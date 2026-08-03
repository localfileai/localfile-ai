"""기능②③ 모델 최적화 전/후 실측 (BE1 3주차 산출물).

계획서 3주차 "답변 생성 속도 및 결과물 품질을 높이기 위한 전반적인 모델 최적화"의
측정 도구다. 3주차에 적용한 최적화 4가지를 각각 켜기 전/후로 재서 표로 낸다.

  [A] 커넥션 재사용 + keep_alive     — 질의 임베딩 지연 (ADR-0002 §5: 고정 오버헤드 96%)
  [B] RAG 컨텍스트 단일 질의          — 예시 검색과 k-NN 분류를 질의 1번 vs 2번
  [C] k-NN 분류 정확도               — 저장된 임베딩 재사용, 같은 주제 배제 (ADR §5-1 재현)
      ※ Ollama 불필요 — 색인에 저장된 벡터로만 계산한다
  [D] full vs slim 생성 시간·토큰     — --with-llm 옵션 (CPU에서 표본당 수십 초)

실행 (색인 필요, [A][B][D]는 Ollama도 필요):
  .venv\\Scripts\\python.exe scripts\\bench_optimization.py            # A+B+C
  .venv\\Scripts\\python.exe scripts\\bench_optimization.py --only C   # Ollama 없이
  .venv\\Scripts\\python.exe scripts\\bench_optimization.py --with-llm # D 포함
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from embed_dataset import COLLECTION_NAME, OllamaEmbeddingFunction

OLLAMA = "http://localhost:11434"
SAMPLE_QUERY = "운영체제 스케줄링 정리한 자료"


def median_ms(samples: list[float]) -> str:
    return f"{statistics.median(samples) * 1000:7.0f}ms"


# ---------------------------------------------------------
# [A] 커넥션 재사용 + keep_alive
# ---------------------------------------------------------

def bench_connection(model: str, repeat: int) -> None:
    print("\n[A] 질의 임베딩 지연 — 커넥션 재사용 + keep_alive")
    print(f"    같은 질의 {repeat}회, 중위값. 첫 회는 모델 로딩이라 버린다.")

    payload = {"model": model, "input": [SAMPLE_QUERY], "keep_alive": "10m"}

    def once(session_or_requests) -> float:
        started = time.perf_counter()
        response = session_or_requests.post(f"{OLLAMA}/api/embed", json=payload, timeout=600)
        response.raise_for_status()
        return time.perf_counter() - started

    requests.post(f"{OLLAMA}/api/embed", json=payload, timeout=600)  # 워밍업

    cold = [once(requests) for _ in range(repeat)]          # 매번 새 커넥션 (1주차 방식)
    with requests.Session() as session:                     # 3주차: 커넥션 재사용
        warm = [once(session) for _ in range(repeat)]

    saved = (statistics.median(cold) - statistics.median(warm)) * 1000
    print(f"    새 커넥션(종전)      : {median_ms(cold)}")
    print(f"    Session 재사용(3주차): {median_ms(warm)}   (중위 {saved:+.0f}ms)")

    # keep_alive 효과: 모델을 내린 직후의 첫 질의 = 사용자가 한참 뒤에 검색할 때
    requests.post(f"{OLLAMA}/api/embed",
                  json={**payload, "keep_alive": 0}, timeout=600)
    started = time.perf_counter()
    requests.post(f"{OLLAMA}/api/embed", json=payload, timeout=600)
    reload_sec = time.perf_counter() - started
    print(f"    모델 내려간 뒤 첫 질의: {reload_sec * 1000:7.0f}ms  <- keep_alive 10m이 없애 주는 비용")


# ---------------------------------------------------------
# [B] RAG 컨텍스트 단일 질의
# ---------------------------------------------------------

def bench_single_query(collection, repeat: int) -> None:
    print("\n[B] RAG 컨텍스트 조회 — 질의 1번(3주차) vs 2번(예시·분류 각각)")

    def query_n(times: int) -> float:
        started = time.perf_counter()
        for _ in range(times):
            collection.query(query_texts=[SAMPLE_QUERY], n_results=6)
        return time.perf_counter() - started

    query_n(1)  # 워밍업
    twice = [query_n(2) for _ in range(repeat)]
    once = [query_n(1) for _ in range(repeat)]
    print(f"    질의 2번(종전 설계)  : {median_ms(twice)}")
    print(f"    질의 1번(retrieve_context): {median_ms(once)}   -> 추천 파일당 임베딩 비용 절반")


# ---------------------------------------------------------
# [C] k-NN 분류 정확도 — 저장된 벡터 재사용 (Ollama 불필요)
# ---------------------------------------------------------

def bench_knn(collection) -> None:
    import numpy as np

    print("\n[C] k-NN 분류 정확도 — 같은 주제 배제 (처음 보는 주제 가정, ADR-0002 §5-1)")

    data = collection.get(include=["embeddings", "metadatas"])
    vectors = np.asarray(data["embeddings"], dtype=np.float32)
    metadatas = data["metadatas"]
    categories = [m["true_category"] for m in metadatas]
    topics = [m.get("topic_title", "") for m in metadatas]
    n = len(vectors)
    print(f"    표본: 색인 전수 {n}건 · 추가 임베딩 비용 0 (저장 벡터 재사용)")

    normalized = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    similarity = normalized @ normalized.T

    for k in (1, 3, 5):
        correct = 0
        for i in range(n):
            scores = similarity[i].copy()
            # 자기 자신 + 같은 주제 전부 배제 — 쌍둥이 문서로 인한 100% 인공물 방지
            for j in range(n):
                if j == i or topics[j] == topics[i]:
                    scores[j] = -2.0
            neighbors = np.argpartition(scores, -k)[-k:]
            votes = Counter(categories[j] for j in neighbors)
            correct += votes.most_common(1)[0][0] == categories[i]
        print(f"    k={k}: {correct}/{n} = {correct / n:.1%}")
    majority = Counter(categories).most_common(1)[0][1]
    print(f"    (기준선 — 최빈 클래스: {majority / n:.1%} · 무작위: {1 / len(set(categories)):.1%})")


# ---------------------------------------------------------
# [D] full vs slim 생성 시간·토큰
# ---------------------------------------------------------

def bench_llm(models: tuple[str, str], sample: int, timeout: int) -> None:
    import csv as csv_module

    from app.llm.prompts import SYSTEM_PROMPT_FULL, SYSTEM_PROMPT_SLIM, build_user_prompt

    print(f"\n[D] LLM 생성 — full({models[0]}) vs slim({models[1]}) · 표본 {sample}건")

    csv_path = Path("dataset") / "dataset.csv"
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [r for r in csv_module.DictReader(handle)
                if r["extraction_status"] == "success"][:sample]

    for label, model, system in (("full", models[0], SYSTEM_PROMPT_FULL),
                                 ("slim", models[1], SYSTEM_PROMPT_SLIM)):
        times, tokens = [], []
        for row in rows:
            prompt = build_user_prompt(
                current_name=row["current_name"], current_path=row["current_path"],
                extension=row["extension"], first_page_text=row["first_page_text"])
            started = time.perf_counter()
            response = requests.post(f"{OLLAMA}/api/generate", json={
                "model": model, "system": system, "prompt": prompt,
                "format": "json", "stream": False,
                "options": {"temperature": 0.1}, "keep_alive": "10m",
            }, timeout=timeout)
            response.raise_for_status()
            times.append(time.perf_counter() - started)
            tokens.append(response.json().get("eval_count", 0))
        print(f"    {label:<5} {model:<18}: 중위 {statistics.median(times):6.1f}s · "
              f"평균 출력 {statistics.mean(tokens):5.0f}토큰")


def main() -> int:
    parser = argparse.ArgumentParser(description="모델 최적화 전/후 실측")
    parser.add_argument("--db", type=Path, default=Path("./chroma_db"))
    parser.add_argument("--embed-model", default="bge-m3")
    parser.add_argument("--repeat", type=int, default=7, help="[A][B] 반복 횟수")
    parser.add_argument("--only", choices=["A", "B", "C", "D"], help="한 항목만")
    parser.add_argument("--with-llm", action="store_true", help="[D] 포함 (CPU 수 분)")
    parser.add_argument("--llm-models", nargs=2, metavar=("FULL", "SLIM"),
                        default=("exaone3.5:7.8b", "exaone3.5:2.4b"))
    parser.add_argument("--llm-sample", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    if not args.db.exists():
        print(f"[에러] 색인 없음: {args.db} — `npm run index` 먼저", file=sys.stderr)
        return 1

    import chromadb
    client = chromadb.PersistentClient(path=str(args.db))
    collection = client.get_collection(
        COLLECTION_NAME, embedding_function=OllamaEmbeddingFunction(args.embed_model))
    print(f"[색인] {collection.count()}건 · {args.embed_model}")

    run = lambda key: args.only in (None, key)  # noqa: E731
    if run("A"):
        bench_connection(args.embed_model, args.repeat)
    if run("B"):
        bench_single_query(collection, args.repeat)
    if run("C"):
        bench_knn(collection)
    if run("D") and (args.with_llm or args.only == "D"):
        bench_llm(tuple(args.llm_models), args.llm_sample, args.timeout)
    elif args.only is None:
        print("\n[D] LLM 비교는 --with-llm 을 주면 실행한다 (CPU에서 수 분).")

    print("\n결과는 docs/weekly/week-03.md 의 측정 기록 표에 옮겨 적는다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
