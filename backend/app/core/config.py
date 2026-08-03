"""Ollama·모델 설정의 단일 출처.

ADR-0002 §3 후속 조치: "2주차에 Mock을 실제 Ollama 연동으로 바꿀 때
`OLLAMA_GENERATE_MODEL` / `OLLAMA_EMBED_MODEL`을 설정 한 곳에 모으고,
기본값을 `exaone3.5:7.8b` / `bge-m3` 로 두어야 한다."

여기 있는 값이 코드 전체의 기본값이다. 환경 변수로만 바꾼다.
"""

from __future__ import annotations

import os

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# 임베딩 모델 (기능① 검색). ADR-0002 §2.
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "bge-m3")

# 추천용 로컬 LLM (기능②③). ADR-0002 §1.
OLLAMA_GENERATE_MODEL = os.getenv("OLLAMA_GENERATE_MODEL", "exaone3.5:7.8b")

# 저사양(GPU 없음) 대책용 소형 모델. ADR-0002 §5-1.
# ⚠️ 품질 재측정 전이므로 기본 경로에서는 쓰지 않는다 (mode="slim" 선택 시에만).
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
