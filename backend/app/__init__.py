"""FastAPI 앱을 생성하는 함수를 제공하는 파일입니다."""


def create_app():
    """서버 실행 시 사용할 FastAPI 앱 인스턴스를 만듭니다."""
    # 전처리 스크립트는 FastAPI 없이도 실행될 수 있어야 합니다.
    # 그래서 서버 실행에 필요한 import는 create_app 안에서만 수행합니다.
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from .api.routes import health, mock, organize, preprocess, search

    app = FastAPI(title="Local File AI Backend")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 기본 서버 확인용 라우터입니다.
    app.include_router(health.router)

    # FE가 백엔드 연동을 먼저 테스트할 수 있도록 더미 데이터를 제공합니다.
    app.include_router(mock.router)

    # PDF/TXT/MD 파일에서 텍스트를 추출하는 1주차 BE2 핵심 API입니다.
    app.include_router(preprocess.router)

    # 실제 임베딩 기반 자연어 검색입니다 (BE1 기능①).
    # ChromaDB 색인이 없으면 503과 함께 이유를 돌려주므로, 없어도 서버는 뜹니다.
    app.include_router(search.router)

    # 실제 분류·파일명 추천입니다 (BE1 기능②③, 3주차).
    # Ollama 생성 모델이 없으면 503과 함께 이유를 돌려주므로, 없어도 서버는 뜹니다.
    app.include_router(organize.router)
    return app
