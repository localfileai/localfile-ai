"""
프로젝트 루트 엔트리 포인트
- `app` 패키지에서 FastAPI 앱 인스턴스를 가져와 uvicorn이 불러올 수 있게 합니다.
Usage: `uvicorn main:app --reload --host 127.0.0.1 --port 8000`
"""

from app import app

