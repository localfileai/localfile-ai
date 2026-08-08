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
import re
from dataclasses import dataclass
from typing import Callable

from pydantic import ValidationError

from ..contracts.ai import Category, FileSuggestion, RetrievedExample
from .client import LLMRequestError
from .prompts import (
    SYSTEM_PROMPT_FULL,
    SYSTEM_PROMPT_SLIM,
    build_retry_prompt,
    build_slim_user_prompt,
    build_user_prompt,
    format_violations,
)

# 재시도는 정확히 1회다. CPU에서 호출당 수십 초라 더 늘리면 대기가 감당되지 않는다.
GenerateFn = Callable[[str, str], str]

_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_CATEGORY_DOCUMENT_TYPE = {
    Category.LECTURE: "강의자료", Category.ASSIGNMENT: "과제",
    Category.REPORT: "보고서", Category.REFERENCE: "참고자료",
    Category.PROJECT: "프로젝트", Category.EXAM_PREP: "시험정리",
    Category.CAREER: "취업문서", Category.ADMIN: "행정문서",
    Category.PERSONAL: "개인문서", Category.ETC: "기타",
}
_TERM_GROUPS = (
    ("인공지능", "AI"), ("운영체제", "OS"), ("데이터베이스", "DB"),
    ("컴퓨터네트워크", "네트워크", "NETWORK"),
)
_SEMANTIC_STOPWORDS = {
    "문서", "자료", "최종", "과제", "강의자료", "보고서", "참고자료",
    "프로젝트", "시험정리", "취업문서", "행정문서", "개인문서", "기타",
}


def _clean_component(value: object) -> str:
    """LLM 구성요소를 파일명에 안전한 한 구간으로 정규화한다."""
    text = _INVALID_FILENAME_CHARS.sub(" ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip(" ._")
    return text.replace(" ", "_")


def _flat_evidence(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", text).lower()


def _supported_component(value: str, evidence: str) -> str:
    """subject/topic의 중요한 토큰이 실제 문서에 있을 때만 유지한다."""
    cleaned = _clean_component(value)
    tokens = [token for token in cleaned.split("_")
              if len(token) >= 2 and token not in _SEMANTIC_STOPWORDS]
    return cleaned if tokens and all(_flat_evidence(token) in evidence for token in tokens) else ""


def _document_semester(text: str) -> str:
    match = re.search(r"(20\d{2})\s*(?:[-./년]\s*)?([12])\s*(?:학기)?", text)
    return f"{match.group(1)}-{match.group(2)}" if match else ""


def _preferred_spelling(value: str, examples: list[RetrievedExample] | None) -> str:
    """승인·유사 파일명에 반복된 한글/영문 표기를 현재 구성요소에 적용한다."""
    if not value or not examples:
        return value
    # 임의의 영문 용어도 사용자가 승인한 대소문자를 그대로 따른다.
    for example in examples:
        for token in re.split(r"[_\s.()\-]+", example.file_name):
            if token.lower() == value.lower():
                return token
    lowered = value.lower()
    for group in _TERM_GROUPS:
        if lowered not in {term.lower() for term in group}:
            continue
        for example in examples:
            tokens = re.split(r"[_\s.()\-]+", example.file_name)
            for token in tokens:
                if token.lower() in {term.lower() for term in group}:
                    return token
    return value


def _preferred_separator(examples: list[RetrievedExample] | None) -> str:
    """예시 파일명 다수에서 사용한 `_`/`-` 구분자를 선택한다."""
    if not examples:
        return "_"
    underscores = sum(example.file_name.count("_") for example in examples)
    hyphens = sum(example.file_name.rsplit(".", 1)[0].count("-") for example in examples)
    return "-" if hyphens > underscores else "_"


def _split_known_subject(value: str, evidence: str) -> tuple[str, str]:
    """`인공지능 트랜스포머`처럼 합쳐진 subject에서 검증 가능한 topic을 복구한다."""
    cleaned = _clean_component(value)
    lowered = cleaned.lower()
    for group in _TERM_GROUPS:
        for term in group:
            prefix = f"{term.lower()}_"
            if lowered.startswith(prefix):
                topic = cleaned[len(term) + 1:]
                if _supported_component(topic, evidence):
                    return term, topic
    return cleaned, ""


def build_filename(payload: dict, extension: str,
                   category: Category | None = None, *,
                   evidence_text: str = "",
                   examples: list[RetrievedExample] | None = None) -> str:
    """구조화된 LLM 응답을 결정론적으로 조립한다. 구형 파일명 응답도 호환한다."""
    normalized_ext = extension.lower().lstrip(".")
    component_keys = ("subject", "topic", "document_type", "semester")
    has_components = any(key in payload for key in component_keys)

    if has_components:
        values = {key: _clean_component(payload.get(key)) for key in component_keys}
        if evidence_text:
            evidence = _flat_evidence(evidence_text)
            split_subject, recovered_topic = _split_known_subject(
                values["subject"], evidence)
            values["subject"] = split_subject
            values["subject"] = _supported_component(values["subject"], evidence)
            values["topic"] = _supported_component(values["topic"], evidence)
            if not values["topic"] and recovered_topic:
                values["topic"] = recovered_topic
            # 모델이 추측한 학기 대신 본문에서 직접 찾은 학기만 사용한다.
            values["semester"] = _document_semester(evidence_text)
        values["subject"] = _preferred_spelling(values["subject"], examples)
        values["topic"] = _preferred_spelling(values["topic"], examples)
        if category is not None:
            # 분류기가 LLM보다 정확하므로 문서 유형도 최종 분류와 일치시킨다.
            values["document_type"] = _CATEGORY_DOCUMENT_TYPE[category]
        separator = _preferred_separator(examples)
        stem = separator.join(value for value in values.values() if value)
    else:
        legacy = str(payload.get("recommended_filename") or "")
        if legacy.lower().endswith(f".{normalized_ext}"):
            # 정상인 구형 응답은 대소문자를 포함해 그대로 둔다.
            return legacy
        # 기존 확장자가 무엇이든 한 번 제거하고 원본 확장자로 정확히 교체한다.
        # 금지 문자는 여기서 숨기지 않고 Pydantic 검증과 재시도가 잡게 한다.
        stem = legacy.rsplit(".", 1)[0] if "." in legacy else legacy

    if not stem:
        return ""
    if stem.upper() in _WINDOWS_RESERVED:
        stem = f"문서_{stem}"
    # FileSuggestion의 150자 계약 안에서 확장자 공간을 먼저 확보한다.
    stem = stem[:max(1, 149 - len(normalized_ext))].rstrip(" ._")
    return f"{stem}.{normalized_ext}"


def _prepare_payload(raw: str, extension: str,
                     category: Category | None = None, *,
                     evidence_text: str = "",
                     examples: list[RetrievedExample] | None = None) -> tuple[str, bool]:
    """구조화/구형 응답을 최종 FileSuggestion 계약 형태로 바꾼다."""
    try:
        payload = json.loads(raw)
    except Exception:
        return raw, False
    if not isinstance(payload, dict):
        return raw, False

    before = payload.get("recommended_filename")
    filename = build_filename(payload, extension, category,
                              evidence_text=evidence_text, examples=examples)
    for key in ("subject", "topic", "document_type", "semester"):
        payload.pop(key, None)
    payload["recommended_filename"] = filename
    changed = before != filename
    return json.dumps(payload, ensure_ascii=False), changed


@dataclass
class SuggestResult:
    """파일 1건 추천 시도의 결과. suggestion이 None이면 error에 이유가 있다."""

    suggestion: FileSuggestion | None
    retried: bool = False
    filename_normalized: bool = False
    error: str = ""

    @property
    def extension_fixed(self) -> bool:
        """구버전 호출자 호환. 새 코드는 filename_normalized를 사용한다."""
        return self.filename_normalized


def autofix_extension(raw: str, extension: str) -> tuple[str, bool]:
    """recommended_filename에 확장자가 빠졌으면 원본 확장자를 붙인다.

    ADR-0002 "⚠️ 필수 후속 조치" 그 자체다. 프롬프트로 고칠 문제가 아니라
    백엔드가 아는 값을 채우는 후처리가 맞다는 결론이 1주차에 났다.
    """
    return _prepare_payload(raw, extension)


def _short(text: str, limit: int = 180) -> str:
    """FailedFile.reason 계약(200자)에 맞게 자른다."""
    text = " ".join(text.split())
    return text[:limit]


def _attempt_full(raw: str, extension: str,
                  category: Category | None = None, *, evidence_text: str = "",
                  examples: list[RetrievedExample] | None = None) -> tuple[FileSuggestion | None, ValidationError | None, bool]:
    """full 응답 1회분을 보정·검증한다."""
    raw, fixed = _prepare_payload(raw, extension, category,
                                  evidence_text=evidence_text, examples=examples)
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

    suggestion, error, fixed = _attempt_full(
        raw, extension, category, evidence_text=first_page_text, examples=examples)
    if suggestion is not None:
        return SuggestResult(finalize(suggestion), filename_normalized=fixed)

    # 1회 재시도: 위반한 제약을 그대로 보여 준다.
    violations = format_violations(error)
    try:
        raw_retry = generate_fn(
            SYSTEM_PROMPT_FULL, build_retry_prompt(user_prompt, raw, violations))
    except LLMRequestError as exc:
        return SuggestResult(None, retried=True,
                             error=_short(f"llm_request_error(재시도): {exc}"))

    suggestion, error_retry, fixed_retry = _attempt_full(
        raw_retry, extension, category, evidence_text=first_page_text, examples=examples)
    if suggestion is not None:
        return SuggestResult(finalize(suggestion), retried=True,
                             filename_normalized=fixed or fixed_retry)

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
    evidence_text: str = "",
    examples: list[RetrievedExample] | None = None,
) -> tuple[FileSuggestion | None, ValidationError | None, bool]:
    """slim 응답(파일명만)에 자동 분류 결과를 합쳐 full 계약으로 조립·검증한다."""
    raw, fixed = _prepare_payload(raw, extension, category,
                                  evidence_text=evidence_text, examples=examples)
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
    user_prompt = build_slim_user_prompt(
        current_name=current_name,
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
        confidence=confidence, method=method, model_label=model_label,
        evidence_text=first_page_text, examples=examples)
    if suggestion is not None:
        return SuggestResult(suggestion, filename_normalized=fixed)

    violations = format_violations(error)
    try:
        raw_retry = generate_fn(
            SYSTEM_PROMPT_SLIM, build_retry_prompt(user_prompt, raw, violations))
    except LLMRequestError as exc:
        return SuggestResult(None, retried=True,
                             error=_short(f"llm_request_error(재시도): {exc}"))

    suggestion, error_retry, fixed_retry = _assemble_slim(
        raw_retry, extension=extension, category=category,
        confidence=confidence, method=method, model_label=model_label,
        evidence_text=first_page_text, examples=examples)
    if suggestion is not None:
        return SuggestResult(suggestion, retried=True,
                             filename_normalized=fixed or fixed_retry)

    return SuggestResult(
        None, retried=True,
        error=_short(f"llm_invalid_json: {format_violations(error_retry)}"),
    )
