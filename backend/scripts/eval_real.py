"""실파일 분류 실전 검증 — "폴더가 곧 라벨" 방식 (BE1 3주차 산출물).

합성 데이터 정확도(82.8%)가 진짜 파일에서도 나오는지 확인한다.

사용법:
  1) 검증용 폴더를 만들고, 카테고리 이름의 하위 폴더에 **진짜 파일**을 직접
     분류해 넣는다 (넣는 행위가 곧 라벨링이다):

       검증폴더/
       ├─ lecture/      (또는 강의자료/)   ← 진짜 강의자료 몇 개
       ├─ assignment/   (또는 과제/)
       ├─ career/       (또는 자소서/)
       └─ etc/          (또는 기타/)       ← 어디에도 안 맞는 문서

     전 카테고리를 채울 필요 없다. 있는 것만 채점한다.

  2) 실행 (Ollama의 임베딩 모델만 필요 — LLM 불필요, 파일당 1초 미만):
       .venv\\Scripts\\python.exe scripts\\eval_real.py --root "C:/검증폴더"

주의: 파일은 읽기만 하며 이동·수정하지 않는다. 결과는 화면 출력뿐이다.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.contracts.ai import Category
from app.extraction.service import extract_from_path
from app.rag import classify

# 폴더 이름 → 카테고리. 영문 카테고리명과 한국어 별칭을 모두 받는다.
FOLDER_ALIASES = {
    "lecture": Category.LECTURE, "강의자료": Category.LECTURE, "강의": Category.LECTURE,
    "assignment": Category.ASSIGNMENT, "과제": Category.ASSIGNMENT,
    "report": Category.REPORT, "보고서": Category.REPORT, "실험보고서": Category.REPORT,
    "reference": Category.REFERENCE, "논문": Category.REFERENCE, "참고자료": Category.REFERENCE,
    "project": Category.PROJECT, "프로젝트": Category.PROJECT,
    "exam_prep": Category.EXAM_PREP, "시험정리": Category.EXAM_PREP, "시험": Category.EXAM_PREP,
    "career": Category.CAREER, "자소서": Category.CAREER, "취업": Category.CAREER,
    "admin": Category.ADMIN, "행정": Category.ADMIN, "학사": Category.ADMIN,
    "personal": Category.PERSONAL, "개인": Category.PERSONAL, "생활": Category.PERSONAL,
    "etc": Category.ETC, "기타": Category.ETC,
}


def judge_mode(root: Path, limit: int, feedback) -> int:
    """대화형 검증 — 폴더 준비 없이 진짜 폴더를 그대로 가리킨다.

    파일마다 분류 결과를 보여주고 사용자가 Enter(맞음)/n(틀림)만 누른다.
    파일은 읽기만 하며 이동·수정하지 않는다.
    """
    import os

    items = extract_from_path(str(root), max_chars=2000)
    usable = [item for item in items
              if not item["error"] and (item["normalized_text"] or item["raw_text"]).strip()]
    # 최근 파일부터 — 사용자가 기억하는 파일이라 판정이 빠르다.
    usable.sort(key=lambda item: os.path.getmtime(item["path"])
                if os.path.isfile(item["path"]) else 0, reverse=True)
    usable = usable[:limit]
    if not usable:
        print("[에러] 처리할 수 있는 문서가 없습니다.", file=sys.stderr)
        return 1

    print(f"대상 {len(usable)}개 (최근 파일부터). 파일마다 분류가 맞는지 판정해 주세요.")
    print("  Enter=맞음 · n=틀림 · s=이 파일 모름/건너뜀 · q=여기까지만 하고 집계\n")

    results = []
    for number, item in enumerate(usable, start=1):
        text = (item["normalized_text"] or item["raw_text"]).strip()
        decision, _ = classify.classify_text(text, feedback)
        snippet = " ".join(text.split())[:70]
        print(f"[{number}/{len(usable)}] {item['name']}")
        print(f"   내용: {snippet}...")
        print(f"   분류: {decision.category.value}  (신뢰도 {decision.confidence:.2f} · {decision.method})")
        answer = input("   맞나요? [Enter/n/s/q] ").strip().lower()
        print()
        if answer == "q":
            break
        if answer == "s":
            continue
        results.append((answer != "n", decision))

    if not results:
        print("[에러] 판정된 파일이 없습니다.", file=sys.stderr)
        return 1

    n = len(results)
    correct = sum(1 for ok, _ in results if ok)
    print("=" * 70)
    print(f"실파일 분류 정확도 (사용자 판정): {correct}/{n} = {correct / n:.1%}"
          f"   (합성 데이터 기준 82.8%)")
    print("=" * 70)
    wrong = Counter(decision.category.value for ok, decision in results if not ok)
    if wrong:
        print("틀렸다고 판정된 분류:", dict(wrong))
    etc_count = sum(1 for _, decision in results if decision.category is Category.ETC)
    print(f"etc(분류 보류) 처리: {etc_count}건")
    print("\n이 결과를 docs/weekly/week-03.md 실전 검증 항목에 기록한다.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="실파일 분류 검증")
    parser.add_argument("--root", type=Path, required=True,
                        help="검증할 폴더 (--judge면 아무 실폴더, 아니면 카테고리 하위 폴더 구조)")
    parser.add_argument("--judge", action="store_true",
                        help="대화형 모드 — 폴더 준비 없이 파일마다 Enter/n으로 판정")
    parser.add_argument("--limit", type=int, default=30, help="--judge 모드 최대 파일 수")
    parser.add_argument("--use-feedback", action="store_true",
                        help="쌓인 사용자 피드백 예시도 참조해 분류 (기본: 순수 zero-shot)")
    args = parser.parse_args()

    root = args.root.expanduser()
    if not root.is_dir():
        print(f"[에러] 폴더가 아닙니다: {root}", file=sys.stderr)
        return 1

    feedback_col = None
    if args.use_feedback:
        from app.rag.search import feedback_collection
        feedback_col = feedback_collection()

    if args.judge:
        return judge_mode(root, args.limit, feedback_col)

    labeled_dirs = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and child.name.lower() in FOLDER_ALIASES:
            labeled_dirs.append((FOLDER_ALIASES[child.name.lower()], child))
    if not labeled_dirs:
        print(f"[에러] 카테고리 이름의 하위 폴더가 없습니다. 예: {root}/lecture, {root}/과제",
              file=sys.stderr)
        print(f"       인식하는 이름: {', '.join(sorted(set(FOLDER_ALIASES)))}", file=sys.stderr)
        return 1

    results: list[tuple[Category, Category, str, float, str]] = []
    skipped = 0

    for truth, directory in labeled_dirs:
        items = extract_from_path(str(directory), max_chars=2000)
        for item in items:
            text = (item["normalized_text"] or item["raw_text"]).strip()
            if item["error"] or not text:
                skipped += 1
                print(f"  [건너뜀] {item['name']}  ({item['error'] or '텍스트 없음'})")
                continue
            decision, _ = classify.classify_text(text, feedback_col)
            mark = "O" if decision.category is truth else "X"
            print(f"  [{mark}] {truth.value:<10} -> {decision.category.value:<10} "
                  f"({decision.confidence:.2f} · {decision.method})  {item['name'][:30]}")
            results.append((truth, decision.category, item["name"],
                            decision.confidence, decision.method))

    if not results:
        print("[에러] 채점할 파일이 없습니다.", file=sys.stderr)
        return 1

    n = len(results)
    correct = sum(1 for truth, predicted, *_ in results if truth is predicted)
    print()
    print("=" * 70)
    print(f"실파일 분류 정확도: {correct}/{n} = {correct / n:.1%}"
          f"   (합성 데이터 기준은 82.8%)")
    print("=" * 70)

    per = defaultdict(lambda: [0, 0])
    for truth, predicted, *_ in results:
        per[truth][1] += 1
        per[truth][0] += truth is predicted
    for category in sorted(per, key=lambda c: -per[c][1]):
        hit, total = per[category]
        print(f"  {category.value:<12} {hit:>3}/{total:<3} = {hit / total:.1%}")

    confusions = Counter((truth.value, predicted.value)
                         for truth, predicted, *_ in results if truth is not predicted)
    if confusions:
        print("\n자주 틀리는 조합:")
        for (truth, predicted), count in confusions.most_common(5):
            print(f"  {truth} -> {predicted} : {count}건")
    if skipped:
        print(f"\n건너뜀 {skipped}건 (추출 실패·빈 텍스트)")
    print("\n이 결과를 docs/weekly/week-03.md 실전 검증 항목에 기록한다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
