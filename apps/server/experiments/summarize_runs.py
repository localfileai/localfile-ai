"""실험 결과 CSV들을 읽어 모델별 지표와 오답 패턴을 한눈에 정리한다."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

RUNS = [
    ("model_test_results.csv", "category / 관례 미제공 (baseline)", "predicted_category"),
    ("model_test_results_with_rule.csv", "category / 관례 제공 (--explain-rule)", "predicted_category"),
    ("model_test_results_subject.csv", "subject / 보조 지표", "predicted_subject"),
]
MODELS = ["exaone3.5:7.8b", "qwen2.5:7b"]


def main() -> None:
    for filename, label, pred_field in RUNS:
        path = Path(filename)
        if not path.exists():
            print(f"\n### {label}\n  (파일 없음: {filename})")
            continue

        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))

        print(f"\n### {label}   [{filename}]")
        for model in MODELS:
            subset = [r for r in rows if r["model"] == model]
            if not subset:
                continue
            n = len(subset)
            correct = sum(int(r["is_correct"]) for r in subset)
            valid = sum(int(r["json_valid"]) for r in subset)
            avg = sum(float(r["elapsed_sec"]) for r in subset) / n

            print(f"  {model:<16} 정확도 {correct:>2}/{n} ({correct / n:>5.1%})   "
                  f"JSON {valid:>2}/{n} ({valid / n:>5.1%})   평균 {avg:.2f}s")

            preds = Counter(r[pred_field] for r in subset if r[pred_field])
            top = ", ".join(f"{k}={v}" for k, v in preds.most_common(4))
            print(f"      예측 상위: {top}")

            errors = Counter(r["error"] for r in subset if r["error"])
            if errors:
                for err, count in errors.most_common():
                    print(f"      오류 {count}건: {err}")


if __name__ == "__main__":
    main()
