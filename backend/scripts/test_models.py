"""기능②③ 베이스 모델 선정 실험 — Ollama 로컬 LLM 프롬프트 테스트.

BE1 1주차 산출물 ③. 계획안: "학습용 베이스 모델 선정 및 Ollama 기본 모델로
프롬프트 테스트 진행".

측정 지표
  ② 분류 정확도      : true_category 와 일치한 비율
  ③ 파일명 품질      : 구성요소 점수(과목/주제/문서유형/학기가 들어갔는가) + 토큰 F1
  공통 JSON 유효율   : schemas.FileSuggestion 통과율
  공통 평균 응답 시간

옵션 --with-rag 를 주면 ChromaDB에서 유사 문서 3건을 찾아 프롬프트에 넣는다.
1주차는 기본(RAG 없음)으로 베이스라인을 잡고, 2주차 RAG 적용 효과와 비교한다.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import statistics
import sys
import time
from pathlib import Path

import requests
from pydantic import ValidationError

# 스크립트를 `python scripts/...` 형태로 실행해도 app 패키지를 import할 수 있게 합니다.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.contracts.ai import MAX_FIRST_PAGE_CHARS, FileSuggestion
from app.llm.prompts import build_retry_prompt, format_violations

OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
DEFAULT_MODELS = ["exaone3.5:7.8b", "qwen2.5:7b", "llama3.1:8b"]

CATEGORY_GUIDE = """- lecture     : 강의자료, 수업 노트
- assignment  : 제출용 과제
- report      : 실험 보고서, 결과 분석
- reference   : 논문 요약, 참고자료
- project     : 프로젝트 계획서, 설계 문서
- exam_prep   : 시험 정리, 요약 노트"""

SYSTEM_PROMPT = f"""당신은 어질러진 개인 문서를 정리해 주는 파일 정리 전문가입니다.
사용자의 파일은 "최종.pdf", "무제.txt"처럼 이름만 봐서는 내용을 알 수 없습니다.
첫 페이지 텍스트를 읽고 어느 폴더에 어떤 이름으로 보관할지 판단하십시오.

반드시 아래 JSON 객체 하나만 출력하십시오. 설명, 인사말, 마크다운 코드펜스 등
JSON 외의 문자는 절대 출력하지 마십시오.

{{
  "category": "<아래 6개 중 정확히 하나>",
  "recommended_folder": "<상대 경로. 예: lecture/운영체제/2025-1>",
  "recommended_filename": "<확장자를 포함한 새 파일명>",
  "confidence": <0.0 이상 1.0 이하의 실수>,
  "reason": "<한국어 1~200자 근거>"
}}

category는 다음 6개 값 중 하나여야 하며, 그 외의 값은 허용되지 않습니다.
{CATEGORY_GUIDE}

recommended_filename 규칙:
- 과목명, 문서 주제, 문서 유형, 학기를 밑줄(_)로 이어 붙입니다.
- 원본 확장자를 그대로 유지합니다.
- \\ / : * ? " < > | 문자는 쓸 수 없습니다.
"""


def build_prompt(row: dict, examples: list[dict] | None) -> str:
    parts = [
        f"현재 파일명: {row['current_name']}",
        f"현재 위치: {row['current_path']}",
        f"확장자: {row['extension']}",
        "",
        f"첫 페이지 텍스트 (최대 {MAX_FIRST_PAGE_CHARS}자):",
        "---",
        row["first_page_text"][:MAX_FIRST_PAGE_CHARS],
        "---",
    ]
    if examples:
        parts += ["", "참고: 비슷한 문서들은 이렇게 정리되어 있었습니다."]
        for example in examples:
            parts.append(
                f"  - {example['ideal_filename']}  ->  {example['true_category']} 폴더")
    parts += ["", "이 파일을 분석해 JSON 한 개만 출력하십시오."]
    return "\n".join(parts)


def check_ollama(models: list[str]) -> list[str]:
    try:
        response = requests.get(OLLAMA_TAGS_URL, timeout=10)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        print(
            "\n[에러] Ollama 서버에 연결할 수 없습니다 (http://localhost:11434).\n"
            "  1) 설치 확인: ollama --version   (미설치 시 https://ollama.com/download)\n"
            "  2) 서버 실행: ollama serve\n",
            file=sys.stderr,
        )
        raise SystemExit(2)

    installed = {m["name"] for m in response.json().get("models", [])}
    print(f"[Ollama] 연결 성공. 설치된 모델 {len(installed)}개")

    available = []
    for model in models:
        tag = model if ":" in model else f"{model}:latest"
        if tag in installed:
            available.append(model)
        else:
            print(f"[경고] 미설치로 건너뜁니다: {model}   (설치: ollama pull {model})")
    if not available:
        print("\n[에러] 실험할 모델이 없습니다.\n", file=sys.stderr)
        raise SystemExit(2)
    return available


def call_model(model: str, system: str, prompt: str, timeout: int) -> tuple[str | None, float, str]:
    payload = {
        "model": model, "system": system, "prompt": prompt,
        "format": "json", "stream": False, "options": {"temperature": 0.1},
    }
    started = time.perf_counter()
    try:
        response = requests.post(OLLAMA_GENERATE_URL, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json().get("response", ""), time.perf_counter() - started, ""
    except requests.exceptions.Timeout:
        return None, time.perf_counter() - started, f"timeout({timeout}s)"
    except requests.exceptions.RequestException as error:
        return None, time.perf_counter() - started, f"request_error: {type(error).__name__}"


# ---------------------------------------------------------
# ③ 파일명 채점
# ---------------------------------------------------------

def autofix_extension(raw: str, extension: str) -> tuple[str, bool]:
    """recommended_filename에 확장자가 빠졌으면 붙여 준다.

    모델이 파일명 내용은 제대로 만들면서 확장자만 빠뜨리는 사례가 잦다.
    실제 서비스에서는 원본 확장자를 아는 쪽이 백엔드이므로 후처리로 해결하는 게 맞다.
    이 함수를 켜고 껐을 때의 차이가 곧 '프롬프트로 고칠 문제인가'의 답이 된다.
    """
    try:
        payload = json.loads(raw)
    except Exception:
        return raw, False

    name = payload.get("recommended_filename")
    if not isinstance(name, str) or name.lower().endswith(f".{extension}"):
        return raw, False

    payload["recommended_filename"] = f"{name}.{extension}"
    return json.dumps(payload, ensure_ascii=False), True


def tokenize(name: str) -> set[str]:
    stem = re.sub(r"\.(pdf|txt|md)$", "", name, flags=re.IGNORECASE)
    return {t for t in re.split(r"[_\s\-()]+", stem) if t}


def score_filename(predicted: str, row: dict) -> tuple[float, dict]:
    """구성요소 점수(0~1)와 세부 내역을 돌려준다.

    정답 규칙이 '과목_주제_문서유형_학기.확장자'이므로 각 구성요소가
    예측 파일명에 들어갔는지를 본다. 순서나 구분자는 따지지 않는다.
    """
    lowered = predicted.lower()
    checks = {
        "course": row["course"] in predicted,
        "topic": any(word in predicted for word in row["topic_title"].split() if len(word) > 1),
        "doc_type": row["doc_type"].replace(" ", "") in predicted.replace(" ", "").replace("_", ""),
        "semester": row["semester"] in predicted,
        "extension": lowered.endswith(f".{row['extension']}"),
    }
    return sum(checks.values()) / len(checks), checks


def token_f1(predicted: str, ideal: str) -> float:
    p, g = tokenize(predicted), tokenize(ideal)
    if not p or not g:
        return 0.0
    overlap = len(p & g)
    if not overlap:
        return 0.0
    precision, recall = overlap / len(p), overlap / len(g)
    return 2 * precision * recall / (precision + recall)


# ---------------------------------------------------------

def sample_rows(csv_path: Path, size: int, seed: int) -> list[dict]:
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if r["extraction_status"] == "success"]
    if not rows:
        raise SystemExit("[에러] 추출 성공 행이 없습니다.")
    unique = {r["index"]: r for r in rows}
    pool = sorted(unique.values(), key=lambda r: int(r["index"]))
    return random.Random(seed).sample(pool, min(size, len(pool)))


def load_rag(db_path: Path, model: str):
    import chromadb
    from embed_dataset import COLLECTION_NAME, OllamaEmbeddingFunction

    client = chromadb.PersistentClient(path=str(db_path))
    return client.get_collection(COLLECTION_NAME,
                                 embedding_function=OllamaEmbeddingFunction(model))


def main() -> int:
    parser = argparse.ArgumentParser(description="기능②③ 베이스 모델 선정 실험")
    parser.add_argument("--csv", type=Path, default=Path("dataset") / "dataset.csv")
    parser.add_argument("--sample", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--output", type=Path, default=Path("model_test_results.csv"))
    parser.add_argument("--with-rag", action="store_true",
                        help="ChromaDB 유사 문서 3건을 프롬프트에 포함 (2주차 비교용)")
    parser.add_argument("--db", type=Path, default=Path("./chroma_db"))
    parser.add_argument("--embed-model", default="qwen3-embedding:0.6b")
    parser.add_argument("--autofix-extension", action="store_true",
                        help="확장자가 빠진 파일명에 원본 확장자를 붙여 준 뒤 검증한다.")
    parser.add_argument("--retry", action="store_true",
                        help="검증 실패 시 위반 제약을 명시해 1회 재시도한다 (3주차 재시도 로직 측정).")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"[에러] CSV 없음: {args.csv}", file=sys.stderr)
        return 1

    models = check_ollama(args.models)
    rows = sample_rows(args.csv, args.sample, args.seed)
    collection = load_rag(args.db, args.embed_model) if args.with_rag else None

    print(f"[샘플] seed={args.seed} 로 {len(rows)}건")
    print(f"[모델] {models}")
    print(f"[RAG ] {'유사 문서 3건 주입' if args.with_rag else '없음 (1주차 베이스라인)'}")
    print("범례: O=분류 정답 / △=형식만 통과 / X=형식 깨짐\n")

    records: list[dict] = []
    summary: list[dict] = []

    for model in models:
        print("=" * 82)
        print(f"모델: {model}   (첫 호출은 모델 로딩으로 1~2분 걸릴 수 있습니다)")
        print("=" * 82)

        correct = valid = fixed = 0
        retry_attempts = retry_saves = 0
        name_scores: list[float] = []
        f1_scores: list[float] = []
        times: list[float] = []

        def validate(raw_text: str) -> tuple:
            """(parsed, 에러 문자열, 확장자 보정 여부, ValidationError)"""
            did_fix = False
            if args.autofix_extension:
                raw_text, did_fix = autofix_extension(raw_text, row["extension"])
            try:
                return FileSuggestion.model_validate_json(raw_text), "", did_fix, None
            except ValidationError as exc:
                first = exc.errors()[0]
                loc = ".".join(str(p) for p in first["loc"])
                return None, f"validation: {loc} {first['type']}", did_fix, exc
            except Exception as exc:
                return None, f"parse_error: {type(exc).__name__}", did_fix, None

        for i, row in enumerate(rows, start=1):
            examples = None
            if collection is not None:
                found = collection.query(query_texts=[row["first_page_text"][:1500]],
                                         n_results=4)
                examples = [m for m in found["metadatas"][0]
                            if m["current_name"] != row["current_name"]][:3]

            prompt = build_prompt(row, examples)
            raw, elapsed, error = call_model(model, SYSTEM_PROMPT, prompt, args.timeout)

            parsed = None
            retried = False
            if raw is not None:
                parsed, verror, did_fix, vexc = validate(raw)
                fixed += did_fix
                if parsed is None:
                    error = verror
                    # 3주차 재시도 로직: 위반한 제약을 명시해 정확히 1회 재시도한다.
                    # app/llm/suggest.py의 런타임 로직과 같은 프롬프트를 쓴다.
                    if args.retry and vexc is not None:
                        retried = True
                        retry_attempts += 1
                        raw2, elapsed2, error2 = call_model(
                            model, SYSTEM_PROMPT,
                            build_retry_prompt(prompt, raw, format_violations(vexc)),
                            args.timeout)
                        elapsed += elapsed2
                        if raw2 is not None:
                            parsed, verror2, did_fix2, _ = validate(raw2)
                            fixed += did_fix2
                            if parsed is not None:
                                retry_saves += 1
                                error = ""
                            else:
                                error = f"{verror2} (재시도 후에도 실패)"
                        else:
                            error = f"재시도 호출 실패: {error2}"
            times.append(elapsed)

            if parsed is None:
                mark, predicted_cat, name_score, f1, checks = "X", "", 0.0, 0.0, {}
            else:
                valid += 1
                predicted_cat = parsed.category.value
                is_correct = predicted_cat == row["true_category"]
                correct += is_correct
                mark = "O" if is_correct else "△"
                name_score, checks = score_filename(parsed.recommended_filename, row)
                f1 = token_f1(parsed.recommended_filename, row["ideal_filename"])
                name_scores.append(name_score)
                f1_scores.append(f1)

            print(f"  [{i:>3}/{len(rows)}] {mark} {elapsed:6.2f}s  "
                  f"분류 {row['true_category']:<11}->{predicted_cat or '-':<11} "
                  f"파일명 {name_score:4.0%}  {row['current_name'][:16]}"
                  + (f"  ({error})" if error else ""))

            records.append({
                "model": model, "with_rag": int(bool(collection)), "index": row["index"],
                "current_name": row["current_name"], "extension": row["extension"],
                "true_category": row["true_category"], "predicted_category": predicted_cat,
                "category_correct": int(parsed is not None and predicted_cat == row["true_category"]),
                "ideal_filename": row["ideal_filename"],
                "predicted_filename": parsed.recommended_filename if parsed else "",
                "filename_score": round(name_score, 3), "filename_token_f1": round(f1, 3),
                "filename_checks": json.dumps(checks, ensure_ascii=False),
                "json_valid": int(parsed is not None),
                "retried": int(retried),
                "confidence": parsed.confidence if parsed else "",
                "recommended_folder": parsed.recommended_folder if parsed else "",
                "reason": parsed.reason if parsed else "",
                "elapsed_sec": round(elapsed, 3), "error": error,
            })

        n = len(rows)
        summary.append({
            "model": model,
            "category_accuracy": correct / n,
            "filename_score": statistics.mean(name_scores) if name_scores else 0.0,
            "filename_token_f1": statistics.mean(f1_scores) if f1_scores else 0.0,
            "json_valid_rate": valid / n,
            "avg_sec": statistics.mean(times),
        })
        print(f"\n  -> {model}: 분류 {correct}/{n} ({correct / n:.1%}) · "
              f"파일명 {statistics.mean(name_scores) if name_scores else 0:.1%} · "
              f"JSON {valid}/{n} ({valid / n:.1%}) · 평균 {statistics.mean(times):.2f}s"
              + (f" · 확장자 보정 {fixed}건" if args.autofix_extension else "")
              + (f" · 재시도 {retry_attempts}건 중 {retry_saves}건 구제" if args.retry else "")
              + "\n")

    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)
    print(f"[저장] 건별 결과 {len(records)}행 -> {args.output.resolve()}")

    print("\n" + "=" * 92)
    print(f"베이스 모델 비교표  (샘플 {len(rows)}건 · RAG {'적용' if collection else '없음'})")
    print("=" * 92)
    print(f"{'모델':<20}{'② 분류 정확도':>15}{'③ 파일명 점수':>15}"
          f"{'파일명 토큰F1':>14}{'JSON 유효율':>13}{'평균 응답':>11}")
    print("-" * 92)
    for item in summary:
        print(f"{item['model']:<20}{item['category_accuracy']:>14.1%}"
              f"{item['filename_score']:>15.1%}{item['filename_token_f1']:>14.1%}"
              f"{item['json_valid_rate']:>13.1%}{item['avg_sec']:>10.2f}s")
    print("=" * 92)

    best = max(summary, key=lambda s: (
        s["category_accuracy"] + s["filename_score"], s["json_valid_rate"], -s["avg_sec"]))
    print(f"\n선정: {best['model']}")
    print(f"  분류 {best['category_accuracy']:.1%} · 파일명 {best['filename_score']:.1%} · "
          f"JSON {best['json_valid_rate']:.1%} · {best['avg_sec']:.2f}s")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
