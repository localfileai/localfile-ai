"""기능① 유사도 검색 품질 평가 — 어려운 평가셋 (BE1 3주차 산출물).

ADR-0002 §2가 남긴 단서를 해소한다:
  "평가셋이 쉬운 편입니다. 질의 키워드가 본문에 등장합니다.
   실제 사용자 파일은 주제가 겹치고 표현이 흐릿해 더 어렵습니다."

그래서 평가셋(`data/search_eval_hard.jsonl`)을 두 난이도로 나눴다.
  keyword    : 구어체이지만 주제 핵심어가 1개 들어 있음 (1주차 평가셋 수준)
  paraphrase : 핵심어를 하나도 쓰지 않은 완전한 바꿔 말하기
               예) "정규화" 대신 "테이블 나눠서 중복 없애는 방법"

paraphrase 점수가 진짜 의미 검색 능력이다. 키워드가 본문에 없으므로
문자 일치로는 못 찾고, 임베딩이 뜻을 이해해야만 맞을 수 있다.

실행 (Ollama + 색인 필요):
  .venv\\Scripts\\python.exe scripts\\eval_search.py
  .venv\\Scripts\\python.exe scripts\\eval_search.py --top-k 5 --output eval_results.csv

정답 판정: 검색된 문서의 메타데이터 topic_title 이 평가 항목과 같으면 관련 문서.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from embed_dataset import COLLECTION_NAME, OllamaEmbeddingFunction, check_ollama


def load_eval_set(path: Path) -> list[dict]:
    items = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def evaluate(collection, items: list[dict], top_k: int) -> list[dict]:
    results = []
    for i, item in enumerate(items, start=1):
        started = time.perf_counter()
        found = collection.query(query_texts=[item["query"]], n_results=top_k)
        elapsed_ms = (time.perf_counter() - started) * 1000

        topics = [str((m or {}).get("topic_title", ""))
                  for m in found["metadatas"][0]]
        relevant = [t == item["topic_title"] for t in topics]

        first_hit = relevant.index(True) + 1 if True in relevant else 0
        row = {
            "difficulty": item["difficulty"],
            "query": item["query"],
            "expected_topic": item["topic_title"],
            "top1_topic": topics[0] if topics else "",
            "hit_at_1": int(first_hit == 1),
            f"hit_at_{top_k}": int(first_hit > 0),
            "reciprocal_rank": 1.0 / first_hit if first_hit else 0.0,
            f"relevant_in_top{top_k}": sum(relevant),
            "elapsed_ms": round(elapsed_ms, 1),
        }
        results.append(row)

        mark = "O" if first_hit == 1 else ("△" if first_hit else "X")
        print(f"  [{i:>2}/{len(items)}] {mark} {elapsed_ms:7.0f}ms  "
              f"({item['difficulty']:<10}) {item['query'][:34]}")
    return results


def summarize(results: list[dict], top_k: int) -> None:
    print()
    print("=" * 88)
    print(f"검색 품질 요약 — 어려운 평가셋 {len(results)}건 · top_k={top_k}")
    print("=" * 88)
    header = (f"{'난이도':<12}{'건수':>5}{'Top-1':>9}{f'Recall@{top_k}':>11}"
              f"{'MRR':>8}{f'P@{top_k}':>8}{'중위 지연':>11}")
    print(header)
    print("-" * 88)

    def line(label: str, rows: list[dict]) -> None:
        if not rows:
            return
        n = len(rows)
        print(f"{label:<12}{n:>5}"
              f"{sum(r['hit_at_1'] for r in rows) / n:>9.1%}"
              f"{sum(r[f'hit_at_{top_k}'] for r in rows) / n:>11.1%}"
              f"{statistics.mean(r['reciprocal_rank'] for r in rows):>8.3f}"
              f"{statistics.mean(r[f'relevant_in_top{top_k}'] / top_k for r in rows):>8.1%}"
              f"{statistics.median(r['elapsed_ms'] for r in rows):>9.0f}ms")

    for difficulty in ("keyword", "paraphrase"):
        line(difficulty, [r for r in results if r["difficulty"] == difficulty])
    line("전체", results)
    print("=" * 88)
    print("keyword 대비 paraphrase 하락 폭이 곧 '문자 일치가 아니라 의미를 이해하는가'다.")
    print("1주차 쉬운 평가셋의 100%와 이 수치를 함께 기록해야 검색 품질을 정직하게 말할 수 있다.")


def main() -> int:
    parser = argparse.ArgumentParser(description="기능① 검색 품질 평가 (어려운 평가셋)")
    parser.add_argument("--eval-set", type=Path,
                        default=Path(__file__).parent / "data" / "search_eval_hard.jsonl")
    parser.add_argument("--db", type=Path, default=Path("./chroma_db"))
    parser.add_argument("--embed-model", default="qwen3-embedding:0.6b")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("search_eval_results.csv"))
    args = parser.parse_args()

    if not args.eval_set.exists():
        print(f"[에러] 평가셋 없음: {args.eval_set}", file=sys.stderr)
        return 1
    if not args.db.exists():
        print(f"[에러] 색인 없음: {args.db} — `npm run index` 먼저", file=sys.stderr)
        return 1

    check_ollama(args.embed_model)

    import chromadb
    client = chromadb.PersistentClient(path=str(args.db))
    collection = client.get_collection(
        COLLECTION_NAME, embedding_function=OllamaEmbeddingFunction(args.embed_model))

    items = load_eval_set(args.eval_set)
    print(f"[평가] {len(items)}건 (keyword {sum(1 for i in items if i['difficulty'] == 'keyword')} · "
          f"paraphrase {sum(1 for i in items if i['difficulty'] == 'paraphrase')})")
    print(f"[색인] {collection.count()}건 · 모델 {args.embed_model}\n")

    results = evaluate(collection, items, args.top_k)

    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"\n[저장] 건별 결과 -> {args.output.resolve()}")

    summarize(results, args.top_k)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
