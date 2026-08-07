"""기능② 분류 3방식 비교 — 라벨 누출 제거 데이터셋 기준 (BE1 3주차 산출물).

같은 색인·같은 조건에서 세 분류 방식을 비교한다.

  knn    : 색인 저장 벡터 LOO, 같은 주제 배제 (참조 데이터셋 필요, 비용 0)
  label  : 라벨 정의문 zero-shot (참조 데이터 불필요, 비용 0) — classify.py 방식
  llm    : LLM 직접 추론 (--with-llm, 표본 제한 — 파일당 수 초)

etc 문서(설명서·공지 등)는 label 방식에서 "임계값 미달 → etc"로 맞혀야 한다.
임계값 보정을 돕기 위해 유사도 분포도 출력한다.

실행 (재생성·재색인된 데이터셋 기준):
  .venv\\Scripts\\python.exe scripts\\eval_classify.py
  .venv\\Scripts\\python.exe scripts\\eval_classify.py --with-llm --sample 40
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from embed_dataset import COLLECTION_NAME, OllamaEmbeddingFunction

from app.rag.classify import LABEL_DEFINITIONS


def load_vectors(collection):
    import numpy as np

    data = collection.get(include=["embeddings", "metadatas", "documents"])
    vectors = np.asarray(data["embeddings"], dtype=np.float32)
    vectors = vectors / np.clip(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9, None)
    return vectors, data["metadatas"], data["documents"]


def report(name: str, results: list[tuple[str, str]]) -> None:
    """(정답, 예측) 목록으로 전체·카테고리별 정확도를 출력한다."""
    n = len(results)
    correct = sum(1 for truth, predicted in results if truth == predicted)
    print(f"\n[{name}] 전체 정확도: {correct}/{n} = {correct / n:.1%}")
    per = defaultdict(lambda: [0, 0])
    for truth, predicted in results:
        per[truth][1] += 1
        per[truth][0] += truth == predicted
    for category in sorted(per, key=lambda c: -per[c][1]):
        hit, total = per[category]
        print(f"    {category:<12} {hit:>4}/{total:<4} = {hit / total:.1%}")


def eval_knn(vectors, metadatas, k: int = 3) -> list[tuple[str, str]]:
    import numpy as np

    categories = [m["true_category"] for m in metadatas]
    topics = [m.get("topic_title", "") for m in metadatas]
    similarity = vectors @ vectors.T
    results = []
    for i in range(len(vectors)):
        scores = similarity[i].copy()
        for j in range(len(vectors)):
            if j == i or topics[j] == topics[i]:
                scores[j] = -2.0
        neighbors = np.argpartition(scores, -k)[-k:]
        predicted = Counter(categories[j] for j in neighbors).most_common(1)[0][0]
        results.append((categories[i], predicted))
    return results


def eval_label(vectors, metadatas, embed_model: str, threshold: float):
    import numpy as np

    labels = list(LABEL_DEFINITIONS)
    definitions = [LABEL_DEFINITIONS[label] for label in labels]
    raw = OllamaEmbeddingFunction(embed_model)(definitions)
    label_matrix = np.asarray(raw, dtype=np.float32)
    label_matrix = label_matrix / np.clip(
        np.linalg.norm(label_matrix, axis=1, keepdims=True), 1e-9, None)

    similarities = vectors @ label_matrix.T           # (n_docs, n_labels)
    best_index = similarities.argmax(axis=1)
    best_similarity = similarities.max(axis=1)

    results = []
    in_domain_sims, etc_sims = [], []
    for i, metadata in enumerate(metadatas):
        truth = metadata["true_category"]
        predicted = (labels[best_index[i]].value
                     if best_similarity[i] >= threshold else "etc")
        results.append((truth, predicted))
        (etc_sims if truth == "etc" else in_domain_sims).append(float(best_similarity[i]))

    print("\n[label] 임계값 보정 참고 — 최고 유사도 분포")
    for name, sims in (("정상(9종)", in_domain_sims), ("etc 문서", etc_sims)):
        if sims:
            q = statistics.quantiles(sims, n=10)
            print(f"    {name:<10} 하위10% {q[0]:.3f} · 중위 {statistics.median(sims):.3f} · "
                  f"상위10% {q[-1]:.3f}")
    print(f"    현재 임계값 {threshold} — 정상 하위10%보다 낮고 etc 중위보다 높아야 이상적")
    return results


def eval_llm(metadatas, documents, sample: int, model: str, timeout: int):
    import json
    import random

    import requests

    from app.llm.prompts import SYSTEM_PROMPT_FULL, build_user_prompt

    rng = random.Random(42)
    picked = rng.sample(range(len(metadatas)), min(sample, len(metadatas)))
    results = []
    for count, i in enumerate(picked, start=1):
        metadata, document = metadatas[i], documents[i]
        prompt = build_user_prompt(
            current_name=metadata.get("current_name", "무제.pdf"),
            current_path=metadata.get("current_path", ""),
            extension=metadata.get("extension", "pdf"),
            first_page_text=document or "")
        try:
            response = requests.post("http://localhost:11434/api/generate", json={
                "model": model, "system": SYSTEM_PROMPT_FULL, "prompt": prompt,
                "format": "json", "stream": False,
                "options": {"temperature": 0.1}, "keep_alive": "10m"}, timeout=timeout)
            response.raise_for_status()
            predicted = json.loads(response.json().get("response", "{}")).get("category", "")
        except Exception:
            predicted = ""
        results.append((metadata["true_category"], predicted))
        print(f"    [{count}/{len(picked)}] {metadata['true_category']:<10} -> {predicted}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="분류 3방식 비교 (knn / label / llm)")
    parser.add_argument("--db", type=Path, default=Path("./chroma_db"))
    parser.add_argument("--embed-model", default="qwen3-embedding:0.6b")
    parser.add_argument("--threshold", type=float, default=None,
                        help="label 방식 etc 임계값 (기본: config.CLASSIFY_MIN_SIMILARITY)")
    parser.add_argument("--with-llm", action="store_true")
    parser.add_argument("--llm-model", default="exaone3.5:7.8b")
    parser.add_argument("--sample", type=int, default=40, help="llm 방식 표본 수")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    from app.core import config

    threshold = args.threshold if args.threshold is not None else config.CLASSIFY_MIN_SIMILARITY

    import chromadb
    client = chromadb.PersistentClient(path=str(args.db))
    collection = client.get_collection(
        COLLECTION_NAME, embedding_function=OllamaEmbeddingFunction(args.embed_model))
    vectors, metadatas, documents = load_vectors(collection)
    print(f"[색인] {len(vectors)}건 · {args.embed_model} · "
          f"카테고리 {len(set(m['true_category'] for m in metadatas))}종")

    report("knn (같은 주제 배제, k=3)", eval_knn(vectors, metadatas))
    report(f"label zero-shot (임계값 {threshold})",
           eval_label(vectors, metadatas, args.embed_model, threshold))
    if args.with_llm:
        report(f"llm ({args.llm_model}, 표본 {args.sample})",
               eval_llm(metadatas, documents, args.sample, args.llm_model, args.timeout))
    else:
        print("\n[llm] --with-llm 을 주면 LLM 직접 분류도 잰다 (표본당 수 초).")

    print("\n결과는 docs/weekly/week-03.md 분류 재측정 표에 기록한다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
