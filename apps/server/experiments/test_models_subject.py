"""3단계 보조 실험: 판별력 있는 지표로 모델을 재비교한다.

배경
  본 실험(test_models.py)의 category 정확도는 모델을 구분하지 못한다.
  데이터셋의 category가 문서 내용과 독립적으로 무작위 배정되기 때문이다
  (analyze_label_signal.py 참고, 정보 이득 0.036 bit).

  반면 subject(전공 분야, 10분류)는 문서 제목·본문을 결정하는 축이므로 내용에서
  실제로 판별 가능하다. 같은 샘플·같은 호출 조건으로 subject 분류 정확도를 재서
  모델 선정의 근거로 삼는다.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.contracts import MAX_FIRST_PAGE_TEXT
from test_models import DEFAULT_MODELS, check_ollama, query_model, sample_rows

SUBJECT_VALUES = [
    "artificial_intelligence",
    "computer_science",
    "cyber_security",
    "data_science",
    "database",
    "embedded_system",
    "mobile_programming",
    "network",
    "software_engineering",
    "web_programming",
]

Subject = Enum("Subject", {v.upper(): v for v in SUBJECT_VALUES}, type=str)


class SubjectOutput(BaseModel):
    """보조 실험용 출력 계약."""

    model_config = ConfigDict(extra="forbid")

    subject: Subject = Field(..., description="10개 전공 분야 중 하나")
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str = Field(..., min_length=1, max_length=200)


SYSTEM_PROMPT = f"""당신은 학생의 컴퓨터 파일을 정리해 주는 '파일 정리 전문가'입니다.
주어진 파일의 이름, 확장자, 첫 페이지 텍스트를 읽고 이 문서가 어느 전공 분야에 속하는지 판단하십시오.

반드시 아래 JSON 객체 하나만 출력하십시오. 설명, 인사말, 마크다운 코드펜스 등 JSON 외의 문자는 절대 출력하지 마십시오.

{{
  "subject": "<아래 10개 중 정확히 하나>",
  "confidence": <0.0 이상 1.0 이하의 실수>,
  "reason": "<한국어 1~200자 근거>"
}}

subject는 반드시 다음 10개 값 중 하나여야 하며, 그 외의 값은 허용되지 않습니다:
{", ".join(SUBJECT_VALUES)}
"""


def build_user_prompt(row: dict[str, str]) -> str:
    text = row["first_page_text"][:MAX_FIRST_PAGE_TEXT]
    return (
        f"파일명: {row['file_name']}\n"
        f"확장자: {row['extension']}\n"
        f"첫 페이지 텍스트(최대 {MAX_FIRST_PAGE_TEXT}자):\n"
        f"---\n{text}\n---\n\n"
        "위 파일의 전공 분야를 판단해 JSON 한 개만 출력하십시오."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="subject 분류로 모델 판별력 비교")
    parser.add_argument("--csv", type=Path, default=Path("student_dataset") / "file_metadata.csv")
    parser.add_argument("--sample", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--output", type=Path, default=Path("model_test_results_subject.csv"))
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"[에러] CSV를 찾을 수 없습니다: {args.csv}", file=sys.stderr)
        return 1

    models = check_ollama(args.models)
    # test_models.py와 동일한 시드·크기이므로 정확히 같은 30건이 뽑힌다.
    rows = sample_rows(args.csv, args.sample, args.seed)
    print(f"[샘플] seed={args.seed} 로 고유 {len(rows)}건 (본 실험과 동일 표본)")
    print(f"[과제] subject 10분류 — 무작위 기준선 {1 / len(SUBJECT_VALUES):.1%}")
    print("범례: O=정답 / △=형식만 통과 / X=형식 깨짐\n")

    records: list[dict[str, object]] = []
    summary: list[dict[str, object]] = []

    for model in models:
        print("=" * 72)
        print(f"모델: {model}")
        print("=" * 72)
        correct = valid = 0
        total_time = 0.0

        for i, row in enumerate(rows, start=1):
            raw, elapsed, error = query_model(
                model, row, args.timeout, SYSTEM_PROMPT, build_user_prompt(row)
            )
            total_time += elapsed

            parsed = None
            if raw is not None:
                try:
                    parsed = SubjectOutput.model_validate_json(raw)
                except ValidationError as exc:
                    first = exc.errors()[0]
                    error = f"validation: {'.'.join(str(p) for p in first['loc'])} {first['type']}"
                except Exception as exc:
                    error = f"parse_error: {type(exc).__name__}"

            if parsed is None:
                mark, predicted = "X", ""
            else:
                valid += 1
                predicted = parsed.subject.value
                is_correct = predicted == row["subject"]
                correct += is_correct
                mark = "O" if is_correct else "△"

            print(
                f"  [{i:>3}/{len(rows)}] {mark}  {elapsed:6.2f}s  "
                f"정답={row['subject']:<24} 예측={predicted or '-':<24} {row['file_name'][:34]}"
                + (f"  ({error})" if error else "")
            )

            records.append(
                {
                    "model": model,
                    "index": row["index"],
                    "file_name": row["file_name"],
                    "true_subject": row["subject"],
                    "predicted_subject": predicted,
                    "is_correct": int(parsed is not None and predicted == row["subject"]),
                    "json_valid": int(parsed is not None),
                    "elapsed_sec": round(elapsed, 3),
                    "confidence": parsed.confidence if parsed else "",
                    "reason": parsed.reason if parsed else "",
                    "error": error,
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
            }
        )
        print(f"\n  -> {model}: 정확도 {correct}/{n} ({correct / n:.1%}), "
              f"JSON 유효 {valid}/{n} ({valid / n:.1%}), 평균 {total_time / n:.2f}s\n")

    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)
    print(f"[저장] 상세 결과 {len(records)}행 -> {args.output.resolve()}")

    print("\n" + "=" * 84)
    print("보조 지표 비교표 (subject 10분류)")
    print("=" * 84)
    print(f"{'모델':<22}{'샘플':>6}{'subject 정확도':>18}{'JSON 유효율':>14}{'평균 응답(s)':>14}")
    print("-" * 84)
    for item in summary:
        print(f"{item['model']:<22}{item['samples']:>6}"
              f"{item['accuracy']:>17.1%}{item['json_valid_rate']:>14.1%}{item['avg_sec']:>14.2f}")
    print("=" * 84)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
