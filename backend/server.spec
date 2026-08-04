# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 빌드 사양 — backend를 server.exe 하나로 묶는다 (4주차).

실행:  npm run backend:build-exe   (내부적으로 `pyinstaller server.spec`)
결과:  backend/dist/server.exe  (Windows에서 빌드했을 때)

포함되지 않는 것 (의도된 설계):
  - Ollama와 모델        : 사용자가 별도 설치 (기획안 전제)
  - chroma_db·apply_history : 실행 파일 옆에 런타임 생성 (config.BASE_DIR)

숨은 import가 필요한 이유: chromadb·uvicorn은 문자열 기반 동적 import를
써서 PyInstaller의 정적 분석이 의존성을 못 찾는다. collect_all로 코드·
데이터(마이그레이션 SQL 등)까지 통째로 담아야 실행 시점 에러가 없다.
"""

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for package in ("chromadb", "uvicorn", "fitz", "olefile"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        # 개발·실험 전용 — 배포본 크기를 줄인다
        "pytest", "reportlab", "onnxruntime", "tokenizers",
        "matplotlib", "tkinter",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="server",
    debug=False,
    strip=False,
    upx=False,           # UPX 압축은 백신 오탐이 잦아 끈다
    console=True,        # 콘솔 창에 로그 표시 — 문제 진단용. 최종 배포 때 False 검토
    disable_windowed_traceback=False,
)
