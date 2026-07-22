"""
JSONL 데이터셋을 ChromaDB에 넣는 실험용 스크립트입니다.

BE1/RAG 쪽 작업과 맞닿아 있으므로 1주차 BE2 서버에는 직접 연결하지 않았습니다.
나중에 생성한 가짜 데이터셋을 벡터 DB에 넣어 검색 테스트를 할 때 사용할 수 있습니다.
"""

from pathlib import Path
import json
from tqdm import tqdm


def build(collection_name: str, jsonl_path: str):
    """JSONL 파일을 읽어 지정한 ChromaDB 컬렉션에 인덱싱합니다."""
    try:
        import chromadb
        from chromadb.config import Settings
    except Exception:
        raise RuntimeError("chromadb is required. pip install chromadb")
    try:
        from sentence_transformers import SentenceTransformer
    except Exception:
        raise RuntimeError("sentence-transformers is required. pip install sentence-transformers")

    client = chromadb.Client(Settings(chroma_db_impl="duckdb+parquet", persist_directory="./chroma_db"))
    model = SentenceTransformer("all-MiniLM-L6-v2")

    col = client.get_or_create_collection(name=collection_name)

    path = Path(jsonl_path)
    if not path.exists():
        raise FileNotFoundError(jsonl_path)

    ids, metadatas, documents, embeddings = [], [], [], []
    for line in tqdm(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue

        # generate_fake_dataset.py가 만든 id/question/context/answer 구조를 읽습니다.
        obj = json.loads(line)
        ids.append(str(obj.get("id")))
        doc = obj.get("context", "")
        documents.append(doc)
        metadatas.append({"question": obj.get("question"), "answer": obj.get("answer")})

    # 문서를 한 번에 전부 임베딩하지 않고 배치로 나눠 메모리 사용량을 줄입니다.
    batch_size = 256
    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        emb = model.encode(batch, show_progress_bar=False, convert_to_numpy=True)
        embeddings.extend(emb.tolist())

    col.add(ids=ids, metadatas=metadatas, documents=documents, embeddings=embeddings)
    client.persist()
    print(f"Indexed {len(documents)} documents into collection '{collection_name}'")


if __name__ == "__main__":
    import argparse

    # 예: python scripts/embed_chroma.py local_docs fake_dataset.jsonl
    parser = argparse.ArgumentParser()
    parser.add_argument("collection", type=str, default="local_docs")
    parser.add_argument("jsonl", type=str, default="fake_dataset.jsonl")
    args = parser.parse_args()
    build(args.collection, args.jsonl)
