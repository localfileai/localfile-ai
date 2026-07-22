"""
프로젝트 설정값을 모아두는 파일입니다.

환경변수나 `.env` 파일로 값을 바꿀 수 있게 Pydantic BaseSettings를 사용합니다.
"""
from pydantic import BaseSettings


class Settings(BaseSettings):
    """서버에서 공통으로 사용할 설정값입니다."""

    # ChromaDB 데이터가 저장될 기본 폴더입니다.
    CHROMA_DIR: str = "./chroma_db"

    # 로컬 Ollama 서버 주소입니다. RAG/LLM 연결 단계에서 사용합니다.
    OLLAMA_URL: str = "http://localhost:11434"

    # 개발 중 디버그 플래그입니다.
    DEBUG: bool = True

    class Config:
        # `.env` 파일이 있으면 환경변수처럼 읽어옵니다.
        env_file = ".env"


# 다른 파일에서 `from app.core.config import settings`로 가져다 씁니다.
settings = Settings()
