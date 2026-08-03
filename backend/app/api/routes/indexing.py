"""사용자 폴더 색인 API (BE1 기능① 마지막 조각).

`POST /index`로 폴더를 색인하면 그때부터 `GET /search`가 사용자 실파일을
대상으로 동작한다. 임베딩이 오래 걸리므로(CPU 파일당 약 4.6초) 백그라운드로
돌리고, FE는 `GET /index/status`로 진행률을 그린다.

실시간 감시(파일 생성·삭제 감지)는 계획서상 BE2의 Watchdog 항목이다 —
여기서는 요청 시점 1회 색인 + mtime 증분만 담당한다.
"""

from fastapi import APIRouter, HTTPException

from ...contracts.ai import IndexRequest
from ...rag import indexer

router = APIRouter(prefix="/index", tags=["index"])


@router.get("/status")
async def indexing_status():
    """색인 진행률. running 동안 done/total로 진행 바를 그릴 수 있다."""
    state = indexer.status()
    if state["running"]:
        # Ollama가 요청을 직렬 처리하므로 색인 중 검색은 느려진다 (ADR-0002 §5).
        state["note"] = "색인 중에는 검색 응답이 느려질 수 있습니다."
    return state


@router.post("", status_code=202)
async def start_indexing(request: IndexRequest):
    """폴더 색인을 시작한다. 이미 색인 중이면 409."""
    try:
        return indexer.start(request.path, max_files=request.max_files)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=f"경로가 없습니다: {exc}") from exc
    except indexer.IndexerBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
