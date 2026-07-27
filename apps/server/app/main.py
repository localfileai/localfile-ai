"""FastAPI 진입점.

라우터는 app/api/routes/ 에 파트별로 두고 여기서 등록합니다.
무거운 AI 의존성(chromadb 등)은 모듈 최상단에서 import 하지 마세요.
CI는 ai 익스트라 없이 이 모듈을 import 합니다.
"""

from fastapi import FastAPI

app = FastAPI(
    title="LocalFile AI",
    description="로컬 문서 인덱싱 · 자연어 검색 · 정리 추천",
    version="0.1.0",
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Electron이 서버 기동 완료를 확인하는 엔드포인트.

    FE1의 프로세스 관리 로직이 앱 시작 시 이 엔드포인트를 폴링합니다.
    """
    return {"status": "ok", "version": app.version}
