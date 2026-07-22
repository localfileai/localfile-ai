"""
RAG 검색 API 골격 파일입니다.

의존성(chromadb, sentence-transformers 등)을 엔트리 시점에 즉시 불러오지
않고, 엔드포인트가 호출될 때 런타임으로 로드하도록 변경해 개발 중 서버
시작 실패를 방지합니다.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/rag", tags=["rag"])


class QueryIn(BaseModel):
    """RAG 검색 요청으로 받을 자연어 질의입니다."""

    query: str


@router.post("/search")
async def search(query_in: QueryIn, top_k: int = 5):
    """ChromaDB에서 질의와 유사한 문서를 검색하는 실험용 엔드포인트입니다.

    런타임에 optional dependencies를 임포트하여, 개발 환경에서 해당 라이브러리
    미설치 시에도 서버가 정상 기동하도록 합니다. 라이브러리가 없으면 503 반환.
    """
    try:
        from ..db.chroma_client import get_client
        from ..services.embedding import EmbeddingService
    except Exception:
        raise HTTPException(status_code=503, detail="Optional dependency missing: install 'chromadb' and 'sentence-transformers' in the environment")

    client = get_client()
    col = client.get_or_create_collection(name="local_docs")

    emb = EmbeddingService()
    q_emb = emb.embed_texts([query_in.query])[0].tolist()

    res = col.query(query_embeddings=[q_emb], n_results=top_k, include=["metadatas", "documents"])
    return res
