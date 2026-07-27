"""1단계 검증 스크립트: file_metadata.csv의 행 수·분포·한글 인코딩을 점검한다."""

from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import Counter
from pathlib import Path

SUCCESS_STATUS = "success"
EXPECTED_ROWS = 1000
TOP_LEVEL_CATEGORIES = [
    "project",
    "assignment",
    "essay",
    "research",
    "lecture",
    "reference",
    "practice",
    "team_project",
]

# 한 값이 이 비율을 넘으면 분포가 쏠린 것으로 본다.
SKEW_THRESHOLD = 0.30


def load_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def print_distribution(title: str, counter: Counter, total: int) -> None:
    print(f"\n[{title}] 고유값 {len(counter)}개")
    for value, count in counter.most_common():
        ratio = count / total
        flag = "  <-- 쏠림" if ratio > SKEW_THRESHOLD else ""
        print(f"  {value:<16} {count:>5}건 ({ratio:6.1%}){flag}")


def main() -> int:
    parser = argparse.ArgumentParser(description="학생 데이터셋 CSV 품질 검증")
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("student_dataset") / "file_metadata.csv",
        help="검증할 file_metadata.csv 경로",
    )
    parser.add_argument("--seed", type=int, default=42, help="샘플 추출 시드")
    parser.add_argument("--samples", type=int, default=5, help="본문 확인용 샘플 수")
    args = parser.parse_args()

    csv_path = args.csv.expanduser()
    if not csv_path.exists():
        print(f"[에러] CSV를 찾을 수 없습니다: {csv_path}", file=sys.stderr)
        return 1

    rows = load_rows(csv_path)
    total = len(rows)
    failures: list[str] = []

    print("=" * 72)
    print(f"검증 대상: {csv_path.resolve()}")
    print("=" * 72)

    # (1) 행 수
    print(f"\n[행 수] {total}건 (기대: {EXPECTED_ROWS}건)")
    if total != EXPECTED_ROWS:
        failures.append(f"행 수가 {EXPECTED_ROWS}이 아님 ({total})")

    # (2) extraction_status 분포 — 성공 상태 값은 "success"
    status_counter = Counter(row["extraction_status"] for row in rows)
    print_distribution("extraction_status", status_counter, total)
    success_count = status_counter.get(SUCCESS_STATUS, 0)
    print(f"  -> success 비율: {success_count}/{total} ({success_count / total:.1%})")
    if success_count == 0:
        failures.append('extraction_status에 "success" 값이 하나도 없음')
    if "ok" in status_counter:
        failures.append('예상치 못한 "ok" 상태값이 존재함')

    # (3) category / extension 분포 쏠림
    category_counter = Counter(row["category"] for row in rows)
    extension_counter = Counter(row["extension"] for row in rows)
    print_distribution("category", category_counter, total)
    print_distribution("extension", extension_counter, total)

    missing = set(TOP_LEVEL_CATEGORIES) - set(category_counter)
    if missing:
        failures.append(f"누락된 카테고리: {sorted(missing)}")
    unknown = set(category_counter) - set(TOP_LEVEL_CATEGORIES)
    if unknown:
        failures.append(f"정의되지 않은 카테고리: {sorted(unknown)}")

    for name, counter in (("category", category_counter), ("extension", extension_counter)):
        value, count = counter.most_common(1)[0]
        if count / total > SKEW_THRESHOLD:
            failures.append(f"{name} 분포 쏠림: {value} {count / total:.1%}")

    # (4) first_page_text 한글 인코딩 확인
    rng = random.Random(args.seed)
    sample_rows = rng.sample(rows, min(args.samples, total))
    print(f"\n[first_page_text 무작위 {len(sample_rows)}행]")
    for row in sample_rows:
        text = row["first_page_text"]
        preview = text[:120].replace("\n", " ⏎ ")
        has_hangul = any("가" <= ch <= "힣" for ch in text)
        has_mojibake = "�" in text
        mark = "OK" if has_hangul and not has_mojibake else "확인필요"
        print(f"\n  - [{mark}] {row['file_name']}  ({row['category']}/{row['extension']})")
        print(f"    한글 포함={has_hangul}, 치환문자(U+FFFD)={has_mojibake}, 길이={len(text)}")
        print(f"    {preview}")
        if has_mojibake:
            failures.append(f"{row['file_name']}: 본문에 치환문자 포함")

    # 전체 행에 대한 인코딩 일괄 점검
    mojibake_rows = [row["file_name"] for row in rows if "�" in row["first_page_text"]]
    empty_text_rows = [row["file_name"] for row in rows if not row["first_page_text"].strip()]
    print(f"\n[전체 인코딩] 치환문자 포함 행: {len(mojibake_rows)}건 / 빈 본문: {len(empty_text_rows)}건")
    if mojibake_rows:
        failures.append(f"치환문자 포함 행 {len(mojibake_rows)}건")

    print("\n" + "=" * 72)
    if failures:
        print("검증 결과: 실패")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("검증 결과: 통과 (행 수 / 상태값 / 분포 / 한글 인코딩 모두 정상)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
