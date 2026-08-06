"""첫 실행 준비 API (5주차 배포본).

배포본 사용자는 터미널을 열지 않는다. `ollama pull`이 하던 일을 여기로 옮겨
앱 화면의 버튼 하나에 연결한다. 어떤 모델을 받을지는 PC 사양을 보고 권한다.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...setup import provision

router = APIRouter(prefix="/setup", tags=["setup"])


class DownloadRequest(BaseModel):
    """받을 모델 목록. 비우면 이 PC에 권장되는 구성을 받는다."""

    models: list[str] = Field(default_factory=list)


class SelectRequest(BaseModel):
    model: str = Field(..., min_length=1)


@router.get("/status")
async def setup_status():
    """사양·모델 목록·추천·진행률. FE 준비 화면이 이걸 폴링한다.

    무슨 일이 있어도 200과 형태 맞는 본문을 돌려준다 — 이 조회가 500을 내면
    화면은 "준비 상황을 확인하는 중"에 영영 멈추고, 준비 자동 진행도 그
    상태를 기다리느라 시작조차 못 한다.
    """
    try:
        return provision.status()
    except Exception as exc:
        return provision.fallback_status(exc)


@router.post("/models", status_code=202)
async def download_models(request: DownloadRequest | None = None,
                          include_full: bool = False):
    """없는 모델을 백그라운드로 받는다.

    받기로 한 생성 모델은 그대로 사용 모델로 설정된다.
    """
    try:
        return provision.start_download(include_full=include_full,
                                        models=(request.models if request else None))
    except provision.DownloadBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/select")
async def select_model(request: SelectRequest):
    """이미 받아 둔 모델 중에서 사용할 것을 바꾼다."""
    try:
        return {"selected_model": provision.select_model(request.model)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
