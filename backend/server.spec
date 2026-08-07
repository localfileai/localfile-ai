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
for package in ("chromadb", "uvicorn", "pypdfium2", "olefile"):
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

# onedir로 묶는다 (onefile 아님). onefile은 실행할 때마다 수천 개 파일(~200MB)을
# 임시 폴더에 풀고, 새로 설치된 서명 없는 실행 파일이라 Windows Defender가 그
# 파일들을 전부 실시간 검사한다 — 빠른 PC에서도 첫 기동이 4분을 넘겨, 준비
# 화면 전체가 "앱 시작"에서 몇 분씩 멈춰 보였다 (실제 PC에서 겪었다).
# onedir는 압축 해제·검사가 설치 시점에 한 번만 일어나 기동이 몇 초로 준다.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="server",
    debug=False,
    strip=False,
    upx=False,           # UPX 압축은 백신 오탐이 잦아 끈다
    console=True,        # 콘솔 창에 로그 표시 — 문제 진단용. 최종 배포 때 False 검토
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="server",       # dist/server/ 폴더 — server.exe + _internal/
)
