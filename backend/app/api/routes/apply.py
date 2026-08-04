"""승인 후 파일 변경 API (기능④, BE1 4주차).

기획안: "사용자가 승인한 경우에만 파일명 변경 및 이동 실행".
계약(contracts/ai.py)의 ApplyRequest가 approved=True를 강제하고,
실제 검증·이동·이력은 fileops/apply.py가 담당한다.
"""

from fastapi import APIRouter, HTTPException

from ...contracts.ai import ApplyRequest, ApplyResponse
from ...fileops import apply as fileops

router = APIRouter(prefix="/apply", tags=["apply"])


@router.post("", response_model=ApplyResponse)
async def apply_approved(request: ApplyRequest) -> ApplyResponse:
    """승인된 항목들을 실제로 이동·개명한다. dry_run=True면 검증만.

    항목별 실패(충돌·권한·경로 탈출)는 그 항목만 failed/skipped로 남고
    나머지는 계속 진행된다 — 응답의 items에서 건별 결과를 확인할 것.
    """
    try:
        return fileops.apply_changes(request.root, request.items, request.dry_run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/history")
async def apply_history(limit: int = 20):
    """최근 작업 이력 목록. FE '정리 내역'·undo 대상 선택용."""
    return {"history": fileops.list_history(limit=limit)}


@router.post("/undo")
async def apply_undo(history_id: str = ""):
    """가장 최근(또는 지정한) 작업 1회분을 역순으로 되돌린다."""
    try:
        return fileops.undo(history_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
