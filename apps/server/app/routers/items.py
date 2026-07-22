"""
서버 기본 상태를 확인하는 라우터입니다.

프론트엔드나 팀원이 백엔드 서버가 정상 실행 중인지 빠르게 확인할 때 사용합니다.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/", tags=["root"])
async def read_root():
    """브라우저로 루트 주소에 접근했을 때 서버 실행 여부를 알려줍니다."""
    return {"message": "Local File AI backend is running."}


@router.get("/health", tags=["health"])
async def health():
    """배포/연동 테스트에서 사용하기 쉬운 간단한 상태 확인 엔드포인트입니다."""
    return {"status": "ok"}
