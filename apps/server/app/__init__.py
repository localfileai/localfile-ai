"""
FastAPI 앱을 생성하고 현재 1주차에 사용할 라우터만 등록하는 파일입니다.

BE2 담당 범위인 상태 확인, Mock API, 전처리 API를 연결합니다.
RAG 라우터는 BE1 영역이라 아직 앱에 등록하지 않습니다.
"""

from fastapi import FastAPI

from .routers import items, mock, preprocess


def create_app() -> FastAPI:
    """서버 실행 시 사용할 FastAPI 앱 인스턴스를 만듭니다."""
    app = FastAPI(title="Local File AI Backend")

    # 기본 서버 확인용 라우터입니다.
    app.include_router(items.router)

    # FE가 백엔드 연동을 먼저 테스트할 수 있도록 더미 데이터를 제공합니다.
    app.include_router(mock.router)

    # PDF/TXT/MD 파일에서 텍스트를 추출하는 1주차 BE2 핵심 API입니다.
    app.include_router(preprocess.router)
    return app


# uvicorn main:app 명령에서 import될 실제 앱 객체입니다.
app = create_app()
