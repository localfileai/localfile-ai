"""자연어 검색 API (BE1 기능①).

`/mock/search`(1주차 하드코딩)와 달리 **실제 임베딩 검색**이다.
응답은 BE1의 팀 공용 계약 `SearchResponse`를 그대로 쓴다.

계획서 기준 2주차 BE1 항목("Ollama 모델과 ChromaDB 연동")의 선행 구현이다.
"""

from fastapi import APIRouter, HTTPException, Query

from ...contracts.ai import SearchResponse
from ...rag.search import SearchUnavailable, index_status, search

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/status")
async def search_status():
    """색인·모델 준비 상태. FE가 검색이 왜 안 되는지 표시할 때 쓴다."""
    return index_status()


@router.get("", response_model=SearchResponse)
async def natural_language_search(
    q: str = Query(..., min_length=1, max_length=200, description="자연어 질의"),
    top_k: int = Query(default=20, ge=1, le=100),
    root: str = Query(default="", description="이 폴더에서 색인한 문서만 검색"),
):
    """자연어 질의로 색인된 문서를 관련도 순으로 찾는다."""
    try:
        return search(q, top_k=top_k, root=root)
    except SearchUnavailable as exc:
        # 준비가 안 된 상태는 사용자가 고칠 수 있는 문제이므로 이유를 그대로 전달한다.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
