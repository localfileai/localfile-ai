"""
파일 전처리 API 라우터입니다.

BE2의 1주차 핵심 산출물인 '문서 첫 페이지 텍스트 추출' 기능을 HTTP API로 제공합니다.
FE는 사용자가 선택한 파일/폴더 경로를 이 API에 보내 추출 결과를 화면에 표시할 수 있습니다.
"""

from fastapi import APIRouter, HTTPException, Query

from ..schemas import ExtractPathRequest, ExtractPathResponse, ExtractedDocument
from ..services.fileops import extract_from_path

router = APIRouter(prefix="/preprocess", tags=["preprocess"])


@router.post("/extract-first-page", response_model=ExtractPathResponse)
async def extract_first_page(
    request: ExtractPathRequest,
    max_chars: int = Query(default=1000, ge=1, le=5000),
):
    """파일 하나 또는 폴더 안의 지원 문서에서 미리보기 텍스트를 추출합니다."""
    try:
        items = extract_from_path(request.path, max_chars=max_chars)
    except (FileNotFoundError, ValueError) as exc:
        # 사용자가 잘못된 경로나 지원하지 않는 대상을 보낸 경우 400으로 알려줍니다.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # dict 결과를 Pydantic 응답 모델로 변환해 API 응답 구조를 고정합니다.
    documents = [ExtractedDocument(**item) for item in items]
    return ExtractPathResponse(count=len(documents), items=documents)
