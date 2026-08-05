"""server.exe 엔트리 포인트 (4주차 패키징).

개발 중에는 `uvicorn main:app --reload`(scripts/backend.mjs dev)를 쓰고,
배포본은 이 파일을 PyInstaller로 묶어 실행 파일 하나로 만든다:

    npm run backend:build-exe        (Windows에서 실행 — dist/server.exe 생성)

uvicorn을 문자열("main:app")이 아니라 앱 객체로 직접 실행하는 이유:
PyInstaller onefile 안에서는 모듈 경로 재해석(reload·워커 스폰)이 동작하지
않는다. 단일 프로세스로 앱 객체를 넘기는 방식만 frozen 환경에서 안전하다.
"""

import multiprocessing


def main() -> None:
    import os

    import uvicorn

    from app.core.config import BASE_DIR

    # 작업 폴더를 데이터 폴더로 옮긴다. ChromaDB 1.5.x는 **경로에 한글이 있으면
    # 절대 경로로 색인을 열지 못한다**(app/rag/search.py 주석 참고). 사용자 계정
    # 이름이 한글이면 `C:\\Users\\강인혁\\AppData\\...`가 되므로, 여기서 cwd를
    # 데이터 폴더로 맞춰 두면 상대 경로("chroma_db") 우회가 항상 성립한다.
    os.chdir(BASE_DIR)

    from app import create_app

    uvicorn.run(
        create_app(),
        host=os.getenv("LOCAL_FILE_AI_HOST", "127.0.0.1"),  # 로컬 전용 — 외부 비공개
        port=int(os.getenv("LOCAL_FILE_AI_PORT", "8000")),
        log_level="info",
    )


if __name__ == "__main__":
    # Windows onefile 실행 파일에서 자식 프로세스가 서버를 무한 재실행하는
    # 사고를 막는다. PyInstaller 문서가 요구하는 표준 첫 줄이다.
    multiprocessing.freeze_support()
    main()
