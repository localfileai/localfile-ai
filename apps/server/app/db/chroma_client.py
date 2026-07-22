"""
ChromaDB 연결을 만드는 보조 파일입니다.

RAG 검색/임베딩 단계에서 같은 설정으로 ChromaDB 클라이언트를 재사용하기 위해 분리했습니다.
"""
from typing import Optional
from chromadb.config import Settings


def get_client(persist_directory: Optional[str] = None):
    """지정한 저장 경로를 사용하는 ChromaDB 클라이언트를 반환합니다."""
    import chromadb

    persist = persist_directory or "./chroma_db"
    client = chromadb.Client(Settings(chroma_db_impl="duckdb+parquet", persist_directory=persist))
    return client


def get_or_create_collection(client, name: str):
    """컬렉션이 있으면 가져오고, 없으면 새로 만듭니다."""
    return client.get_or_create_collection(name=name)
