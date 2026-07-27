"""3단계: Ollama 로컬 LLM 2종 이상을 파일 분류 과제로 비교 실험한다.

측정 지표
  1) category 정확도 : 데이터셋 정답 category와 일치한 비율
  2) JSON 유효율     : 응답이 schemas.FileOrganizeOutput 검증을 통과한 비율
  3) 건당 평균 응답 시간
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from pathlib import Path

import requests
from pydantic import ValidationError

from app.contracts import MAX_FIRST_PAGE_TEXT, Category, FileOrganizeOutput

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
SUCCESS_STATUS = "success"
DEFAULT_MODELS = ["exaone3.5:7.8b", "qwen2.5:7b"]

CATEGORY_VALUES = [c.value for c in Category]

SYSTEM_PROMPT = f"""당신은 학생의 컴퓨터 파일을 정리해 주는 '파일 정리 전문가'입니다.
주어진 파일의 이름, 확장자, 첫 페이지 텍스트를 읽고 어디에 어떤 이름으로 보관할지 판단하십시오.

반드시 아래 JSON 객체 하나만 출력하십시오. 설명, 인사말, 마크다운 코드펜스 등 JSON 외의 문자는 절대 출력하지 마십시오.

{{
  "category": "<아래 8개 중 정확히 하나>",
  "recommended_folder": "<추천 폴더 경로>",
  "recommended_filename": "<확장자를 포함한 추천 파일명>",
  "confidence": <0.0 이상 1.0 이하의 실수>,
  "reason": "<한국어 1~200자 근거>"
}}

category는 반드시 다음 8개 값 중 하나여야 하며, 그 외의 값은 허용되지 않습니다:
{", ".join(CATEGORY_VALUES)}

각 category의 의미:
- project: 개인 개발 프로젝트 산출물
- assignment: 제출용 과제물
- essay: 소논문·에세이·감상문
- research: 연구·조사 자료
- lecture: 강의 자료·수업 노트
- reference: 참고 자료·레퍼런스
- practice: 실습·연습 결과물
- team_project: 팀 단위 프로젝트 산출물
"""

# --explain-rule 용 부록. 데이터셋의 폴더 관례를 표로 알려준다.
#
# 프롬프트만 주는 기본 모드는 "모델이 관례를 모르는 상태"의 baseline이고,
# 이 부록을 붙인 모드는 "2주차 RAG가 유사 예시로 관례를 알려준 뒤"의 상한 근사치다.
# 두 수치의 차이가 곧 RAG로 메울 수 있는 여지다.
RULE_APPENDIX = """
이 사용자의 폴더 관례는 다음과 같습니다. 문서에 적힌 "문서 유형"과 "수행 형태"를
찾아 아래 표에서 category를 결정하십시오. 표에 없는 판단은 하지 마십시오.

문서 유형     | 개인 수행    | 팀 수행
-------------|-------------|-------------
과제          | assignment  | team_project
보고서        | essay       | assignment
프로젝트      | project     | team_project
설계 문서     | project     | reference
실험 결과     | practice    | practice
조사 자료     | research    | research
발표 초안     | lecture     | lecture
논문 요약     | reference   | essay
"""


def build_user_prompt(row: dict[str, str]) -> str:
    text = row["first_page_text"][:MAX_FIRST_PAGE_TEXT]
    return (
        f"파일명: {row['file_name']}\n"
        f"확장자: {row['extension']}\n"
        f"첫 페이지 텍스트(최대 {MAX_FIRST_PAGE_TEXT}자):\n"
        f"---\n{text}\n---\n\n"
        "위 파일을 분석해 JSON 한 개만 출력하십시오."
    )


def check_ollama(models: list[str]) -> list[str]:
    """Ollama 서버 연결과 모델 보유 여부를 확인하고, 사용 가능한 모델 목록을 돌려준다."""
    try:
        response = requests.get(OLLAMA_TAGS_URL, timeout=10)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        print(
            "\n[에러] Ollama 서버에 연결할 수 없습니다 (http://localhost:11434).\n"
            "  1) Ollama가 설치되어 있는지 확인하세요: ollama --version\n"
            "     미설치라면 https://ollama.com/download 에서 설치하십시오.\n"
            "  2) 설치되어 있다면 서버를 실행하세요: ollama serve\n"
            "     (Windows에서는 트레이의 Ollama 앱이 켜져 있으면 자동 실행됩니다)\n",
            file=sys.stderr,
        )
        raise SystemExit(2)
    except requests.exceptions.RequestException as exc:
        print(f"\n[에러] Ollama 서버 응답 확인 실패: {exc}\n", file=sys.stderr)
        raise SystemExit(2)

    installed = {m["name"] for m in response.json().get("models", [])}
    print(f"[Ollama] 연결 성공. 설치된 모델 {len(installed)}개: {sorted(installed)}")

    available, missing = [], []
    for model in models:
        # 태그를 생략하면 Ollama가 :latest로 해석하므로 동일 규칙으로 대조한다.
        candidate = model if ":" in model else f"{model}:latest"
        (available if candidate in installed else missing).append(model)

    for model in missing:
        print(f"[경고] 모델 미설치로 건너뜁니다: {model}  (설치: ollama pull {model})")

    if not available:
        print("\n[에러] 실험할 수 있는 모델이 하나도 없습니다. 먼저 ollama pull 로 받아 주세요.\n",
              file=sys.stderr)
        raise SystemExit(2)
    return available


def query_model(
    model: str,
    row: dict[str, str],
    timeout: int,
    system_prompt: str = SYSTEM_PROMPT,
    user_prompt: str | None = None,
) -> tuple[str | None, float, str]:
    """모델을 1회 호출하고 (원본 응답, 소요 시간, 오류 메시지)를 돌려준다."""
    payload = {
        "model": model,
        "system": system_prompt,
        "prompt": user_prompt if user_prompt is not None else build_user_prompt(row),
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.1},
    }
    started = time.perf_counter()
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        response.raise_for_status()
        elapsed = time.perf_counter() - started
        return response.json().get("response", ""), elapsed, ""
    except requests.exceptions.Timeout:
        return None, time.perf_counter() - started, f"timeout({timeout}s)"
    except requests.exceptions.RequestException as exc:
        return None, time.perf_counter() - started, f"request_error: {exc}"


def evaluate(raw: str) -> tuple[FileOrganizeOutput | None, str]:
    """원본 응답을 FileOrganizeOutput으로 검증한다."""
    try:
        return FileOrganizeOutput.model_validate_json(raw), ""
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first["loc"]) or "(model)"
        return None, f"validation: {loc} {first['type']}"
    except Exception as exc:  # JSON 파싱 자체 실패 등
        return None, f"parse_error: {type(exc).__name__}"


def sample_rows(csv_path: Path, size: int, seed: int) -> list[dict[str, str]]:
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if r["extraction_status"] == SUCCESS_STATUS]
    if not rows:
        raise SystemExit("[에러] extraction_status == 'success' 인 행이 없습니다.")
    # index 기준으로 중복 없는 무작위 표본을 뽑는다.
    unique = {row["index"]: row for row in rows}
    pool = sorted(unique.values(), key=lambda r: int(r["index"]))
    return random.Random(seed).sample(pool, min(size, len(pool)))


def main() -> int:
    parser = argparse.ArgumentParser(description="Ollama 로컬 LLM 파일 분류 성능 비교")
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("student_dataset") / "file_metadata.csv",
        help="file_metadata.csv 경로",
    )
    parser.add_argument("--sample", type=int, default=30, help="모델당 평가 샘플 수")
    parser.add_argument("--seed", type=int, default=42, help="샘플링 시드")
    parser.add_argument("--timeout", type=int, default=120, help="호출당 타임아웃(초)")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS, help="비교할 모델 태그")
    parser.add_argument(
        "--output", type=Path, default=Path("model_test_results.csv"), help="상세 결과 CSV 경로"
    )
    parser.add_argument(
        "--explain-rule",
        action="store_true",
        help="폴더 관례 표를 프롬프트에 포함한다 (2주차 RAG가 예시로 알려줄 정보의 상한 근사).",
    )
    args = parser.parse_args()

    system_prompt = SYSTEM_PROMPT + (RULE_APPENDIX if args.explain_rule else "")

    csv_path = args.csv.expanduser()
    if not csv_path.exists():
        print(f"[에러] CSV를 찾을 수 없습니다: {csv_path}", file=sys.stderr)
        return 1

    models = check_ollama(args.models)
    rows = sample_rows(csv_path, args.sample, args.seed)
    print(f"[샘플] seed={args.seed} 로 고유 {len(rows)}건 추출")
    print(f"[모델] {models}")
    print(f"[프롬프트] 폴더 관례 표 {'포함' if args.explain_rule else '미포함(baseline)'}")
    print("범례: O=정답 / △=형식만 통과(카테고리 오답) / X=형식 깨짐\n")

    records: list[dict[str, object]] = []
    summary: list[dict[str, object]] = []

    for model in models:
        print("=" * 72)
        print(f"모델: {model}   (첫 호출은 모델 로딩으로 1~2분 걸릴 수 있습니다)")
        print("=" * 72)

        correct = valid = 0
        total_time = 0.0

        for i, row in enumerate(rows, start=1):
            raw, elapsed, error = query_model(model, row, args.timeout, system_prompt)
            total_time += elapsed

            parsed, verr = (None, error) if raw is None else evaluate(raw)
            error = error or verr

            if parsed is None:
                mark, predicted = "X", ""
            else:
                valid += 1
                predicted = parsed.category.value
                is_correct = predicted == row["category"]
                correct += is_correct
                mark = "O" if is_correct else "△"

            print(
                f"  [{i:>3}/{len(rows)}] {mark}  {elapsed:6.2f}s  "
                f"정답={row['category']:<13} 예측={predicted or '-':<13} {row['file_name'][:40]}"
                + (f"  ({error})" if error else "")
            )

            records.append(
                {
                    "model": model,
                    "index": row["index"],
                    "file_name": row["file_name"],
                    "extension": row["extension"],
                    "true_category": row["category"],
                    "predicted_category": predicted,
                    "is_correct": int(parsed is not None and predicted == row["category"]),
                    "json_valid": int(parsed is not None),
                    "elapsed_sec": round(elapsed, 3),
                    "confidence": parsed.confidence if parsed else "",
                    "recommended_folder": parsed.recommended_folder if parsed else "",
                    "recommended_filename": parsed.recommended_filename if parsed else "",
                    "reason": parsed.reason if parsed else "",
                    "error": error,
                    "raw_response": (raw or "").replace("\n", " ")[:500],
                }
            )

        n = len(rows)
        summary.append(
            {
                "model": model,
                "samples": n,
                "accuracy": correct / n,
                "json_valid_rate": valid / n,
                "avg_sec": total_time / n,
                "total_sec": total_time,
            }
        )
        print(
            f"\n  -> {model}: 정확도 {correct}/{n} ({correct / n:.1%}), "
            f"JSON 유효 {valid}/{n} ({valid / n:.1%}), 평균 {total_time / n:.2f}s\n"
        )

    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)
    print(f"[저장] 상세 결과 {len(records)}행 -> {args.output.resolve()}")

    print("\n" + "=" * 84)
    print("모델 비교표")
    print("=" * 84)
    print(f"{'모델':<22}{'샘플':>6}{'category 정확도':>18}{'JSON 유효율':>14}{'평균 응답(s)':>14}")
    print("-" * 84)
    for item in summary:
        print(
            f"{item['model']:<22}{item['samples']:>6}"
            f"{item['accuracy']:>17.1%}{item['json_valid_rate']:>14.1%}{item['avg_sec']:>14.2f}"
        )
    print("=" * 84)

    best = max(summary, key=lambda s: (s["accuracy"], s["json_valid_rate"], -s["avg_sec"]))
    print(
        f"\n권장: {best['model']}  "
        f"(정확도 {best['accuracy']:.1%}, JSON 유효율 {best['json_valid_rate']:.1%}, "
        f"평균 {best['avg_sec']:.2f}s)"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
