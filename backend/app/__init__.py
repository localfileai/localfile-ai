"""FastAPI 앱을 생성하는 함수를 제공하는 파일입니다."""


def create_app():
    """서버 실행 시 사용할 FastAPI 앱 인스턴스를 만듭니다."""
    # 전처리 스크립트는 FastAPI 없이도 실행될 수 있어야 합니다.
    # 그래서 서버 실행에 필요한 import는 create_app 안에서만 수행합니다.
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from .api.routes import feedback, health, indexing, mock, organize, preprocess, search

    app = FastAPI(title="Local File AI Backend")

    app.add_middleware(
        CORSMiddleware,
        # Vite는 5173이 점유되면 5174, 5175…로 넘어간다. 개발 중 포트가 바뀔 때마다
        # CORS로 막히지 않도록 loopback의 모든 포트를 허용한다 (외부 출처는 여전히 차단).
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
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

    # 사용자 폴더 색인입니다 (BE1 기능①, 3주차). 색인이 생기면 /search가
    # 합성 데이터 대신 사용자 실파일을 대상으로 동작합니다.
    app.include_router(indexing.router)

    # 사용자 피드백입니다 (BE1 기능②③ 맞춤화, 3주차). 승인한 분류가 예시로
    # 쌓여 이후 분류에서 우선 참조됩니다.
    app.include_router(feedback.router)
    return app
