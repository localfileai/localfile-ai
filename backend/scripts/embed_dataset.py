"""ChromaDB 세팅 및 1,000쌍 전수 임베딩.

BE1 1주차 산출물 ①②. 기획안 준수 사항:
  - 임베딩은 ChromaDB 기본 모델(영어 전용)이 아니라 Ollama의 다국어 모델을 쓴다.
  - 외부 유료 API를 쓰지 않는다. 전부 로컬에서 돈다.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import chromadb
import requests
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
DEFAULT_MODEL = "bge-m3"
COLLECTION_NAME = "file_documents"


class OllamaEmbeddingFunction(EmbeddingFunction):
    """Ollama의 다국어 임베딩 모델을 ChromaDB에 물리는 어댑터."""

    def __init__(self, model: str = DEFAULT_MODEL, timeout: int = 600) -> None:
        self._model = model
        self._timeout = timeout

    def name(self) -> str:  # ChromaDB가 설정 저장 시 사용
        return f"ollama-{self._model}"

    def __call__(self, input: Documents) -> Embeddings:
        response = requests.post(
            OLLAMA_EMBED_URL,
            json={"model": self._model, "input": list(input)},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()["embeddings"]


def check_ollama(model: str) -> None:
    try:
        tags = requests.get("http://localhost:11434/api/tags", timeout=10)
        tags.raise_for_status()
    except requests.exceptions.ConnectionError:
        print(
            "\n[에러] Ollama 서버에 연결할 수 없습니다 (http://localhost:11434).\n"
            "  1) 설치 확인: ollama --version   (미설치 시 https://ollama.com/download)\n"
            "  2) 서버 실행: ollama serve\n",
            file=sys.stderr,
        )
        raise SystemExit(2)

    installed = {m["name"].split(":")[0] for m in tags.json().get("models", [])}
    if model.split(":")[0] not in installed:
        print(f"\n[에러] 임베딩 모델이 없습니다: {model}\n  설치: ollama pull {model}\n",
              file=sys.stderr)
        raise SystemExit(2)


def main() -> int:
    parser = argparse.ArgumentParser(description="ChromaDB 임베딩 (다국어 모델)")
    parser.add_argument("--csv", type=Path, default=Path("dataset") / "dataset.csv")
    parser.add_argument("--db", type=Path, default=Path("./chroma_db"))
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama 임베딩 모델")
    parser.add_argument("--limit", type=int, default=0, help="0이면 전수")
    parser.add_argument("--batch", type=int, default=16, help="한 번에 보낼 문서 수")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"[에러] CSV 없음: {args.csv}", file=sys.stderr)
        return 1

    check_ollama(args.model)

    with args.csv.open(encoding="utf-8-sig", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if r["extraction_status"] == "success"]
    if args.limit:
        rows = rows[: args.limit]

    print(f"[입력] {args.csv.resolve()}")
    print(f"[대상] 추출 성공 {len(rows)}건")
    print(f"[모델] {args.model} (Ollama 로컬, 다국어)")

    client = chromadb.PersistentClient(path=str(args.db))
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"[정리] 기존 컬렉션 {COLLECTION_NAME!r} 삭제")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=OllamaEmbeddingFunction(args.model),
        metadata={"hnsw:space": "cosine"},
    )

    started = time.perf_counter()
    for offset in range(0, len(rows), args.batch):
        chunk = rows[offset : offset + args.batch]
        collection.add(
            ids=[r["index"] for r in chunk],
            documents=[r["first_page_text"] for r in chunk],
            metadatas=[
                {
                    "current_name": r["current_name"],
                    "current_path": r["current_path"],
                    "extension": r["extension"],
                    "true_category": r["true_category"],
                    "ideal_filename": r["ideal_filename"],
                    "doc_type": r["doc_type"],
                    "course": r["course"],
                    "topic_title": r["topic_title"],
                    "semester": r["semester"],
                }
                for r in chunk
            ],
        )
        done = min(offset + args.batch, len(rows))
        elapsed = time.perf_counter() - started
        rate = done / elapsed if elapsed else 0
        eta = (len(rows) - done) / rate if rate else 0
        print(f"  [{done:>4}/{len(rows)}] {elapsed:6.1f}s 경과 · {rate:5.1f}건/s · 남은 {eta:5.1f}s")

    total = time.perf_counter() - started
    print(f"\n[완료] {collection.count()}건 임베딩 · {total:.1f}초 ({len(rows) / total:.1f}건/s)")
    print(f"[저장] {args.db.resolve()}  컬렉션 {COLLECTION_NAME!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
