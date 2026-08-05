"""첫 실행 준비 API (5주차 배포본).

배포본 사용자는 터미널을 열지 않는다. `ollama pull`이 하던 일을 여기로 옮겨
앱 화면의 [준비 시작] 버튼 하나에 연결한다.
"""

from fastapi import APIRouter, HTTPException

from ...setup import provision

router = APIRouter(prefix="/setup", tags=["setup"])


@router.get("/status")
async def setup_status():
    """앱을 쓸 수 있는 상태인지 + 다운로드 진행률. FE 준비 화면이 이걸 폴링한다."""
    return provision.status()


@router.post("/models", status_code=202)
async def download_models(include_full: bool = False):
    """없는 모델을 백그라운드로 받는다.

    include_full=True면 고품질 모델(7.8b)까지 받는다 — GPU가 있을 때만 권장.
    """
    try:
        return provision.start_download(include_full=include_full)
    except provision.DownloadBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
