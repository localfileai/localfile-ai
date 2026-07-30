"""
프로젝트 루트 엔트리 포인트
- FastAPI 앱을 만들어 uvicorn이 불러올 수 있게 합니다.
Usage: `uvicorn main:app --reload --host 127.0.0.1 --port 8000`
"""

from app import create_app


# uvicorn main:app 명령에서 import될 실제 앱 객체입니다.
app = create_app()
