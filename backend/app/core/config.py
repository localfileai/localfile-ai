"""Ollama·모델 설정의 단일 출처.

ADR-0002 §3 후속 조치: "2주차에 Mock을 실제 Ollama 연동으로 바꿀 때
`OLLAMA_GENERATE_MODEL` / `OLLAMA_EMBED_MODEL`을 설정 한 곳에 모으고,
기본값을 `exaone3.5:7.8b` / `bge-m3` 로 두어야 한다."

여기 있는 값이 코드 전체의 기본값이다. 환경 변수로만 바꾼다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _user_data_dir() -> Path:
    """OS가 정한 "이 앱의 사용자 데이터" 폴더."""
    if sys.platform == "win32":
        root = os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = os.getenv("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(root) / "LocalFileAI"


def _base_dir() -> Path:
    """데이터(색인·이력)의 기준 폴더 — 실행 형태에 따라 다르다.

    - 개발 실행: backend/ 폴더 (이 파일 기준 두 단계 위)
    - 설치된 앱(server.exe): 사용자 데이터 폴더 (`%LOCALAPPDATA%\\LocalFileAI` 등)

    실행 파일 옆에 두면 안 되는 이유(설치형 배포에서 드러나는 문제):
      - `C:\\Program Files\\...` 아래는 일반 사용자에게 쓰기 권한이 없어
        색인·이력 저장이 통째로 실패한다.
      - onefile의 `__file__`이 가리키는 _MEIPASS 임시 폴더는 종료 시 삭제된다.
    Electron이 `LOCAL_FILE_AI_HOME`으로 자기 userData 경로를 넘겨주면 그걸 쓴다.
    """
    override = os.getenv("LOCAL_FILE_AI_HOME")
    if override:
        return Path(override).expanduser()
    if getattr(sys, "frozen", False):
        return _user_data_dir()
    return Path(__file__).resolve().parents[2]


BASE_DIR = _base_dir()
BASE_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# 임베딩 모델 (기능① 검색). 3주차 재검토로 bge-m3에서 교체 — ADR-0002 §2 개정.
# 어려운 평가셋에서 paraphrase Top-1 90%(bge-m3 70%), k-NN 89.8%, 크기 절반(639MB).
# ⚠️ 모델을 바꾸면 기존 색인과 호환되지 않는다 — `npm run index`로 재색인할 것.
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "qwen3-embedding:0.6b")

# 기본 임베딩 모델이 그 PC에서 안 돌 때 갈아탈 예비 모델.
#
# `ollama pull`은 레지스트리에서 파일을 받아 오기만 한다 — 실행기(Ollama)가
# 낡았으면 pull은 성공하고 `/api/embed`만 500으로 죽는다. 배포본에서 실제로
# 겪은 상황이고, 우리 설치 과정은 Ollama가 이미 떠 있으면 건드리지 않으므로
# 남의 PC에 몇 년 된 Ollama가 깔려 있으면 그대로 재현된다.
#
# nomic-embed-text는 작고(274MB) 오래돼서 구버전 Ollama와 저사양 PC에서도 돈다.
# 검색 품질은 기본 모델보다 낮지만, 검색이 아예 안 되는 것보다 낫다는 판단이다.
OLLAMA_EMBED_FALLBACKS = [
    name.strip() for name in
    os.getenv("OLLAMA_EMBED_FALLBACKS", "nomic-embed-text").split(",")
    if name.strip()
]

# 추천용 로컬 LLM (기능②③). ADR-0002 §1.
OLLAMA_GENERATE_MODEL = os.getenv("OLLAMA_GENERATE_MODEL", "exaone3.5:7.8b")

# 저사양(GPU 없음) 대책용 소형 모델. ADR-0002 §5-1.
# 3주차 품질 측정으로 확정: 파일명 점수 84%(7.8b full 80%와 동급), 평균 3.4s(GPU).
# slim 경로에서 이 모델은 파일명만 생성한다 — 분류(k-NN)·reason(백엔드)은 별도.
OLLAMA_GENERATE_MODEL_SLIM = os.getenv("OLLAMA_GENERATE_MODEL_SLIM", "exaone3.5:2.4b")

# 요청이 끝나도 모델을 메모리에 유지하는 시간. ADR-0002 §5가 밝힌
# "질의 지연의 96%가 요청당 고정 오버헤드"의 실효 대책 중 하나다.
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "10m")

# CPU 추론 실측이 81초/파일(7.8b full)이라 여유를 두고 잡는다. ADR-0002 §5.
GENERATE_TIMEOUT_SEC = int(os.getenv("LOCAL_FILE_AI_GENERATE_TIMEOUT", "180"))
EMBED_TIMEOUT_SEC = int(os.getenv("LOCAL_FILE_AI_EMBED_TIMEOUT", "600"))

# 추천 기본 모드. ADR-0002 §5-1 "사양별 동작 계층" 참고.
#   full = 7.8b가 5필드 전부 생성 (GPU 실측 4.3초/파일, CPU 81초)
#   slim = k-NN 분류 + 2.4b 파일명만 (CPU 13초/파일 — 저사양 대책)
#   auto = 첫 요청에서 생성 속도를 재보고 느리면 slim으로 자동 강등
RECOMMEND_MODE_DEFAULT = os.getenv("LOCAL_FILE_AI_RECOMMEND_MODE", "auto")

# auto 모드 판정 기준: 16토큰 생성(워밍업 후)이 이 시간을 넘으면 저사양으로 본다.
# GPU 실측(4.3s/128토큰)이면 16토큰에 1초 미만, CPU(81s/143토큰)면 9초 이상이다.
AUTO_SLIM_THRESHOLD_SEC = float(os.getenv("LOCAL_FILE_AI_AUTO_SLIM_THRESHOLD", "5.0"))

# LLM 응답 생성 온도. 실험(test_models.py)과 런타임이 같아야 수치를 비교할 수 있다.
GENERATE_TEMPERATURE = float(os.getenv("LOCAL_FILE_AI_TEMPERATURE", "0.1"))

# 사용자 폴더 색인 시 임베딩에 넣을 텍스트 상한(글자).
# 임베딩 시간은 글자 수에 비례하므로 이 값이 저사양 색인 속도를 직접 좌우한다.
# 800자면 문서 주제 판별에 충분하고, 검색 결과 발췌(matched_text 최대 500자)도 안 깨진다.
INDEX_EMBED_MAX_CHARS = int(os.getenv("LOCAL_FILE_AI_EMBED_MAX_CHARS", "800"))

# --- 분류 (app/rag/classify.py) ---
# 라벨 정의문 zero-shot 채택 하한. 최고 유사도가 이보다 낮으면 etc(분류 보류) —
# "우리가 아는 종류의 문서가 아니다"의 기준선. 모델별 유사도 분포가 달라
# eval_classify.py로 보정한 뒤 조정한다.
CLASSIFY_MIN_SIMILARITY = float(os.getenv("LOCAL_FILE_AI_CLASSIFY_MIN_SIM", "0.35"))
# 사용자 피드백 예시 우선 채택 하한과 이웃 수. 예시는 정의문보다 구체적이라 기준을 높게 둔다.
CLASSIFY_USER_MIN_SIMILARITY = float(os.getenv("LOCAL_FILE_AI_USER_MIN_SIM", "0.55"))
CLASSIFY_USER_KNN_K = int(os.getenv("LOCAL_FILE_AI_USER_KNN_K", "3"))
