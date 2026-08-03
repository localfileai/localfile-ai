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


def main() -> int:
    parser = argparse.ArgumentParser(description="실파일 분류 검증 (폴더가 곧 라벨)")
    parser.add_argument("--root", type=Path, required=True,
                        help="카테고리 하위 폴더들이 들어 있는 검증 폴더")
    parser.add_argument("--use-feedback", action="store_true",
                        help="쌓인 사용자 피드백 예시도 참조해 분류 (기본: 순수 zero-shot)")
    args = parser.parse_args()

    root = args.root.expanduser()
    if not root.is_dir():
        print(f"[에러] 폴더가 아닙니다: {root}", file=sys.stderr)
        return 1

    labeled_dirs = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and child.name.lower() in FOLDER_ALIASES:
            labeled_dirs.append((FOLDER_ALIASES[child.name.lower()], child))
    if not labeled_dirs:
        print(f"[에러] 카테고리 이름의 하위 폴더가 없습니다. 예: {root}/lecture, {root}/과제",
              file=sys.stderr)
        print(f"       인식하는 이름: {', '.join(sorted(set(FOLDER_ALIASES)))}", file=sys.stderr)
        return 1

    feedback = None
    if args.use_feedback:
        from app.rag.search import feedback_collection
        feedback = feedback_collection()

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
            decision, _ = classify.classify_text(text, feedback)
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
