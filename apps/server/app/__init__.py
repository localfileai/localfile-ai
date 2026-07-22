"""FastAPI 앱을 생성하는 함수를 제공하는 파일입니다."""


def create_app():
    """서버 실행 시 사용할 FastAPI 앱 인스턴스를 만듭니다."""
    # 전처리 스크립트는 FastAPI 없이도 실행될 수 있어야 합니다.
    # 그래서 서버 실행에 필요한 import는 create_app 안에서만 수행합니다.
    from fastapi import FastAPI

    from .routers import items, mock, preprocess

    app = FastAPI(title="Local File AI Backend")

    # 기본 서버 확인용 라우터입니다.
    app.include_router(items.router)

    # FE가 백엔드 연동을 먼저 테스트할 수 있도록 더미 데이터를 제공합니다.
    app.include_router(mock.router)

    # PDF/TXT/MD 파일에서 텍스트를 추출하는 1주차 BE2 핵심 API입니다.
    app.include_router(preprocess.router)
    return app
