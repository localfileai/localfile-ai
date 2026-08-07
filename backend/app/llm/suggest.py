"""Pydantic 검증 + 1회 재시도 파이프라인 (계획서 3주차 BE1 ③).

ADR-0002가 exaone 채택의 전제 조건으로 못박은 두 가지가 여기 있다.
  1. **확장자 자동 보정**: exaone은 파일명 내용은 정확하지만 확장자를 자주
     빠뜨린다(1차 측정에서 JSON 유효율 62.5%의 원인 전부). 원본 확장자는
     백엔드가 이미 아는 값이라 후처리로 붙인다. 보정 후 유효율 100%.
  2. **위반 명시 재시도**: 그래도 검증에 실패하면, 위반한 필드와 제약을
     그대로 보여 주며 정확히 1회 재시도한다. 그래도 실패하면 억지로 추천을
     만들지 않고 이유와 함께 실패 처리한다 (`FailedFile`).

LLM 호출은 `generate_fn(system, prompt) -> str`로 주입받는다.
테스트에서는 가짜 함수를, 런타임에서는 `client.generate`를 넣는다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from pydantic import ValidationError

from ..contracts.ai import Category, FileSuggestion, RetrievedExample
from .client import LLMRequestError
from .prompts import (
    SYSTEM_PROMPT_FULL,
    SYSTEM_PROMPT_SLIM,
    build_retry_prompt,
    build_user_prompt,
    format_violations,
)

# 재시도는 정확히 1회다. CPU에서 호출당 수십 초라 더 늘리면 대기가 감당되지 않는다.
GenerateFn = Callable[[str, str], str]


@dataclass
class SuggestResult:
    """파일 1건 추천 시도의 결과. suggestion이 None이면 error에 이유가 있다."""

    suggestion: FileSuggestion | None
    retried: bool = False
    extension_fixed: bool = False
    error: str = ""


def autofix_extension(raw: str, extension: str) -> tuple[str, bool]:
    """recommended_filename에 확장자가 빠졌으면 원본 확장자를 붙인다.

    ADR-0002 "⚠️ 필수 후속 조치" 그 자체다. 프롬프트로 고칠 문제가 아니라
    백엔드가 아는 값을 채우는 후처리가 맞다는 결론이 1주차에 났다.
    """
    try:
        payload = json.loads(raw)
    except Exception:
        return raw, False

    if not isinstance(payload, dict):
        return raw, False

    name = payload.get("recommended_filename")
    normalized = extension.lower().lstrip(".")
    if not isinstance(name, str) or not name or name.lower().endswith(f".{normalized}"):
        return raw, False

    payload["recommended_filename"] = f"{name}.{normalized}"
    return json.dumps(payload, ensure_ascii=False), True


def _short(text: str, limit: int = 180) -> str:
    """FailedFile.reason 계약(200자)에 맞게 자른다."""
    text = " ".join(text.split())
    return text[:limit]


def _attempt_full(raw: str, extension: str) -> tuple[FileSuggestion | None, ValidationError | None, bool]:
    """full 응답 1회분을 보정·검증한다."""
    raw, fixed = autofix_extension(raw, extension)
    try:
        return FileSuggestion.model_validate_json(raw), None, fixed
    except ValidationError as exc:
        return None, exc, fixed


def _apply_classification(suggestion: FileSuggestion, category: Category,
                          confidence: float, method: str) -> FileSuggestion:
    """LLM 출력의 category·folder를 분류기 결과로 덮어쓴다.

    3주차 3파전 실측(누출 제거 데이터): LLM 직접 분류 50% vs 라벨 정의문
    zero-shot 82.8%. 분류는 전 모드에서 분류기(classify.py)가 담당하고,
    LLM은 파일명·세부 경로·근거만 만든다.
    """
    if suggestion.category is category:
        return suggestion

    # 폴더의 첫 구간(분류 폴더)만 교체하고 LLM이 만든 세부 경로(과목·학기)는 살린다.
    # 단 etc는 세부 경로가 의미 없으므로(과목 개념이 없는 문서) 평평하게 둔다.
    rest = "/".join(suggestion.recommended_folder.split("/")[1:])
    folder = category.value if category is Category.ETC or not rest \
        else f"{category.value}/{rest}"

    note = f" (분류: {_METHOD_LABELS.get(method, method)} {confidence:.0%})"
    reason = suggestion.reason[:200 - len(note)] + note

    return FileSuggestion.model_validate({
        "category": category.value,
        "recommended_folder": folder,
        "recommended_filename": suggestion.recommended_filename,
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
        "reason": reason,
    })


def suggest_full(
    generate_fn: GenerateFn,
    *,
    current_name: str,
    current_path: str,
    extension: str,
    first_page_text: str,
    examples: list[RetrievedExample] | None = None,
    category: Category | None = None,
    confidence: float = 0.0,
    method: str = "label_zeroshot",
) -> SuggestResult:
    """full 모드: LLM이 파일명·세부 폴더·근거를 생성한다 (ADR-0002 §1 기준 경로).

    `category`가 주어지면(분류기 결과) LLM의 category·분류 폴더를 그것으로
    덮어쓴다 — LLM 분류(50%)보다 분류기(82.8%)가 정확하다는 실측에 따른 일원화.
    None이면(임베딩 불가 등) LLM 출력을 그대로 쓴다 (폴백).
    """
    user_prompt = build_user_prompt(
        current_name=current_name,
        current_path=current_path,
        extension=extension,
        first_page_text=first_page_text,
        examples=examples,
    )
    if category is not None:
        # 분류를 힌트로 줘서 폴더 세부 경로가 분류와 어긋나지 않게 한다.
        user_prompt += (f"\n\n참고: 이 문서의 분류는 '{category.value}'로 확정되어 있다. "
                        f"recommended_folder는 {category.value}/ 아래로 잡으십시오.")

    def finalize(suggestion: FileSuggestion) -> FileSuggestion:
        if category is None:
            return suggestion
        return _apply_classification(suggestion, category, confidence, method)

    try:
        raw = generate_fn(SYSTEM_PROMPT_FULL, user_prompt)
    except LLMRequestError as exc:
        return SuggestResult(None, error=_short(f"llm_request_error: {exc}"))

    suggestion, error, fixed = _attempt_full(raw, extension)
    if suggestion is not None:
        return SuggestResult(finalize(suggestion), extension_fixed=fixed)

    # 1회 재시도: 위반한 제약을 그대로 보여 준다.
    violations = format_violations(error)
    try:
        raw_retry = generate_fn(
            SYSTEM_PROMPT_FULL, build_retry_prompt(user_prompt, raw, violations))
    except LLMRequestError as exc:
        return SuggestResult(None, retried=True,
                             error=_short(f"llm_request_error(재시도): {exc}"))

    suggestion, error_retry, fixed_retry = _attempt_full(raw_retry, extension)
    if suggestion is not None:
        return SuggestResult(finalize(suggestion), retried=True,
                             extension_fixed=fixed or fixed_retry)

    return SuggestResult(
        None, retried=True,
        error=_short(f"llm_invalid_json: {format_violations(error_retry)}"),
    )


# 분류 방식 표시용 한국어 이름 (classify.ClassifyResult.method 대응)
_METHOD_LABELS = {
    "user_knn": "사용자 승인 예시 기반",
    "label_zeroshot": "라벨 정의문 유사도",
    "etc_fallback": "분류 보류(기타)",
    "knn": "k-NN 다수결",  # 구버전 호환
}


def _assemble_slim(
    raw: str,
    *,
    extension: str,
    category: Category,
    confidence: float,
    method: str,
    model_label: str,
) -> tuple[FileSuggestion | None, ValidationError | None, bool]:
    """slim 응답(파일명만)에 자동 분류 결과를 합쳐 full 계약으로 조립·검증한다."""
    raw, fixed = autofix_extension(raw, extension)
    try:
        payload = json.loads(raw)
        filename = payload.get("recommended_filename", "") if isinstance(payload, dict) else ""
    except Exception:
        filename = ""

    assembled = {
        "category": category.value,
        # 폴더는 분류 폴더를 그대로 쓴다. 세부 경로(과목·학기)는 full 모드의 영역이다.
        "recommended_folder": category.value,
        "recommended_filename": filename,
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
        "reason": (
            f"{_METHOD_LABELS.get(method, method)} 분류 (신뢰도 {confidence:.0%}), "
            f"파일명은 {model_label} 생성 (slim 모드)"
        ),
    }
    try:
        return FileSuggestion.model_validate(assembled), None, fixed
    except ValidationError as exc:
        return None, exc, fixed


def suggest_slim(
    generate_fn: GenerateFn,
    *,
    current_name: str,
    current_path: str,
    extension: str,
    first_page_text: str,
    category: Category,
    confidence: float,
    method: str = "label_zeroshot",
    examples: list[RetrievedExample] | None = None,
    model_label: str = "소형 LLM",
) -> SuggestResult:
    """slim 모드: 분류는 자동 분류기(classify.py), LLM은 파일명만.

    ADR-0002 §5-1 저사양 대책 — CPU 실측 81.1초/파일 → 13.0초/파일.
    2.4b 파일명 품질 84%로 확정됨 (3주차 측정).
    """
    user_prompt = build_user_prompt(
        current_name=current_name,
        current_path=current_path,
        extension=extension,
        first_page_text=first_page_text,
        examples=examples,
    )

    try:
        raw = generate_fn(SYSTEM_PROMPT_SLIM, user_prompt)
    except LLMRequestError as exc:
        return SuggestResult(None, error=_short(f"llm_request_error: {exc}"))

    suggestion, error, fixed = _assemble_slim(
        raw, extension=extension, category=category,
        confidence=confidence, method=method, model_label=model_label)
    if suggestion is not None:
        return SuggestResult(suggestion, extension_fixed=fixed)

    violations = format_violations(error)
    try:
        raw_retry = generate_fn(
            SYSTEM_PROMPT_SLIM, build_retry_prompt(user_prompt, raw, violations))
    except LLMRequestError as exc:
        return SuggestResult(None, retried=True,
                             error=_short(f"llm_request_error(재시도): {exc}"))

    suggestion, error_retry, fixed_retry = _assemble_slim(
        raw_retry, extension=extension, category=category,
        confidence=confidence, method=method, model_label=model_label)
    if suggestion is not None:
        return SuggestResult(suggestion, retried=True, extension_fixed=fixed or fixed_retry)

    return SuggestResult(
        None, retried=True,
        error=_short(f"llm_invalid_json: {format_violations(error_retry)}"),
    )
