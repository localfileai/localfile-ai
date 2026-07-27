"""데이터셋의 category 라벨이 문서 내용에서 결정되는지 정보이론적으로 검증한다.

2026-07-26 생성기 수정 전에는 category가 rng.choice로 무작위 배정되어
정보 이득이 0에 가까웠고, 분류 정확도의 이론적 상한이 무작위 수준이었다.
수정 후에는 (문서 유형, 수행 형태) 두 신호로 category가 완전히 결정되어야 한다.

이 스크립트는 그 사실을 데이터에서 직접 확인한다.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path


def entropy(counter: Counter) -> float:
    total = sum(counter.values())
    if not total:
        return 0.0
    return -sum((c / total) * math.log2(c / total) for c in counter.values() if c)


def conditional_report(
    rows: list[dict[str, str]],
    key_fields: tuple[str, ...],
    label: str,
    h_category: float,
) -> float:
    """주어진 신호로 category를 얼마나 설명할 수 있는지 계산하고 출력한다."""
    groups: dict[tuple[str, ...], Counter] = defaultdict(Counter)
    for row in rows:
        groups[tuple(row[f] for f in key_fields)][row["category"]] += 1

    total = len(rows)
    conditional = sum((sum(c.values()) / total) * entropy(c) for c in groups.values())
    gain = h_category - conditional
    # 각 그룹에서 최빈 category를 찍었을 때의 정확도 = 이 신호가 주는 상한
    ceiling = sum(max(c.values()) for c in groups.values()) / total

    print(f"\n[{label}]")
    print(f"  그룹 수                  = {len(groups)}")
    print(f"  H(category | 신호)       = {conditional:.4f} bit")
    print(f"  정보 이득                = {gain:.4f} bit ({gain / h_category:.1%} of H)")
    print(f"  정확도 상한(최빈값 규칙) = {ceiling:.1%}")
    return ceiling


def main() -> int:
    parser = argparse.ArgumentParser(description="category 라벨의 내용 신호 검증")
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("student_dataset") / "file_metadata.csv",
        help="검증할 file_metadata.csv 경로",
    )
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"[에러] CSV를 찾을 수 없습니다: {args.csv}", file=sys.stderr)
        return 1

    with args.csv.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    has_new_columns = "document_type" in rows[0] and "work_mode" in rows[0]

    categories = Counter(row["category"] for row in rows)
    h_category = entropy(categories)
    n_classes = len(categories)
    majority = max(categories.values()) / len(rows)

    print("=" * 72)
    print(f"검증 대상: {args.csv.resolve()}")
    print("=" * 72)
    print(f"\n전체 {len(rows)}건, category {n_classes}종")
    print(f"  H(category)      = {h_category:.4f} bit (균등 {n_classes}분류 상한 = "
          f"{math.log2(n_classes):.4f} bit)")
    print(f"  무작위 기준선     = {1 / n_classes:.1%}")
    print(f"  최빈 클래스 기준선 = {majority:.1%}  (항상 최빈 category만 찍을 때)")

    if not has_new_columns:
        print(
            "\n[경고] document_type / work_mode 컬럼이 없는 구버전 CSV입니다.\n"
            "       구버전 생성기는 category를 무작위 배정했으므로 이 데이터의\n"
            "       category 정확도는 모델 평가에 사용할 수 없습니다."
        )
        return 1

    ceiling_type = conditional_report(rows, ("document_type",), "신호 1개: 문서 유형만", h_category)
    conditional_report(rows, ("work_mode",), "신호 1개: 수행 형태만", h_category)
    ceiling_both = conditional_report(
        rows, ("document_type", "work_mode"), "신호 2개: 문서 유형 + 수행 형태", h_category
    )

    # 교차표
    print("\n[교차표] (문서 유형 × 수행 형태) -> category")
    table: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for row in rows:
        table[(row["document_type"], row["work_mode"])][row["category"]] += 1

    print(f"  {'문서 유형':<12}{'수행 형태':<8}{'건수':>6}  category (고유값)")
    print("  " + "-" * 62)
    impure = 0
    for (doc_type, work_mode), counter in sorted(table.items()):
        n = sum(counter.values())
        values = sorted(counter)
        if len(values) > 1:
            impure += 1
        print(f"  {doc_type:<12}{work_mode:<8}{n:>6}  {', '.join(values)}")

    print("\n" + "=" * 72)
    ok = True
    if impure:
        print(f"실패: {impure}개 조합이 여러 category에 매핑됨 (규칙이 결정적이지 않음)")
        ok = False
    if ceiling_both < 0.999:
        print(f"실패: 두 신호로도 상한이 {ceiling_both:.1%}에 그침 (100%여야 함)")
        ok = False
    if ceiling_type > 0.95:
        print(f"경고: 문서 유형 하나만으로 상한 {ceiling_type:.1%} — 과제가 너무 쉬움")

    if ok:
        print("통과: category가 (문서 유형, 수행 형태)로 완전히 결정된다.")
        print(f"  무작위 {1 / n_classes:.1%}  <  최빈 클래스 {majority:.1%}"
              f"  <  문서 유형만 {ceiling_type:.1%}  <  두 신호 모두 {ceiling_both:.1%}")
        print("  -> 모델이 두 신호를 모두 읽는지 측정할 수 있는 유효한 평가 과제다.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
