"""FastAPI 엔트리포인트.

Usage: uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
"""

from app import create_app

# uvicorn app.main:app 명령에서 import될 실제 앱 객체입니다.
app = create_app()
