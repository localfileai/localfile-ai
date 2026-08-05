"""서버 시작 시 웜업 (개선안 C, BE1 4주차).

첫 검색이 느린 이유는 검색 자체가 아니라 준비 비용이다 (3주차 실측):
  - Ollama가 임베딩 모델을 메모리에 올리는 시간 (~2초)
  - ChromaDB가 HNSW 색인을 여는 시간
  - 분류용 라벨 정의문 9건의 좌표 계산 (최초 1회)

이 비용을 첫 사용자 요청이 아니라 서버 시작 직후에 백그라운드로 치른다.
서버 기동 자체는 막지 않는다(데몬 스레드) — Ollama가 꺼져 있어도 서버는
정상으로 뜨고, 이유는 첫 요청의 503 응답이 전달한다.

끄기: 환경 변수 LOCAL_FILE_AI_WARMUP=0 (테스트가 이렇게 끈다)
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger("uvicorn.error")


def _warm_up() -> None:
    started = time.perf_counter()
    try:
        # 1) ChromaDB 색인 열기 — Ollama가 없어도 이건 된다 (검색 준비의 절반)
        from ..rag import search

        search.index_status()

        # 2) 임베딩이 이 PC에서 실제로 되는지 확인 — 안 되면 예비 모델로 갈아탄다.
        #    사용자가 폴더를 고르기 전에 끝내 두면, 첫 색인이 그냥 성공한다.
        from ..rag import embedding

        logger.info("검색 모델 확인 중 (Ollama %s)", embedding.ollama_version() or "버전 미확인")
        logger.info("검색 모델 준비: %s", embedding.ensure_usable_model())

        # 3) 임베딩 모델 로드 + 분류 라벨 좌표 캐시 (한 호출로 둘 다 해결)
        from ..rag import classify

        classify._label_vectors()
    except Exception as exc:
        logger.info("웜업 건너뜀 (Ollama/색인 미준비 — 서버 동작에는 지장 없음): %s", exc)
        return
    logger.info("웜업 완료: 임베딩 모델·라벨 좌표·색인 준비 (%.1fs)", time.perf_counter() - started)


def start_warmup_thread() -> threading.Thread:
    """웜업을 백그라운드로 시작한다. 실패해도 서버에 영향이 없다."""
    thread = threading.Thread(target=_warm_up, name="warmup", daemon=True)
    thread.start()
    return thread
