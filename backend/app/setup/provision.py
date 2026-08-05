"""첫 실행 준비: 필요한 AI 모델을 앱이 직접 받아 온다 (5주차 배포본).

지금까지는 사용자가 터미널에서 `ollama pull ...`을 세 번 쳐야 했다.
배포본에서는 그럴 수 없으므로, 같은 일을 API로 옮기고 앱 화면의 버튼
하나에 연결한다. 이 모듈이 그 실체다.

**경량 기본 + 선택 업그레이드** (팀 결정):
  필수 2개(약 2.2GB)만 받아도 전 기능이 동작한다. 분류·검색은 임베딩 모델이
  담당하고 LLM은 파일명 생성에만 쓰이므로, 저사양 PC는 2.4b로 충분하다.
  GPU가 있는 사용자만 7.8b를 추가로 받아 파일명 품질을 올린다.

색인(indexer.py)과 같은 구조다: 오래 걸리는 일은 백그라운드 스레드로 돌리고
FE는 상태를 폴링해 진행 바를 그린다.
"""

from __future__ import annotations

import shutil
import threading

import requests

from ..core import config

# 받아야 할 모델과 그 이유. 근거 수치는 docs/decisions/0002-model-selection.md.
MODEL_PLAN: list[dict] = [
    {
        "name": config.OLLAMA_EMBED_MODEL,
        "role": "embed",
        "required": True,
        "approx_gb": 0.6,
        "purpose": "검색과 문서 분류. 이 모델이 없으면 앱이 동작하지 않습니다.",
    },
    {
        "name": config.OLLAMA_GENERATE_MODEL_SLIM,
        "role": "generate_slim",
        "required": True,
        "approx_gb": 1.6,
        "purpose": "파일명 추천(경량). GPU가 없어도 쓸 수 있습니다.",
    },
    {
        "name": config.OLLAMA_GENERATE_MODEL,
        "role": "generate_full",
        "required": False,
        "approx_gb": 4.8,
        "purpose": "파일명 추천(고품질). GPU가 있을 때 선택해 받으세요.",
    },
]

# 다운로드는 몇 분~수십 분 걸린다. 청크 사이 간격만 제한한다.
_PULL_TIMEOUT = (10, 120)


class DownloadBusy(RuntimeError):
    """이미 다운로드가 진행 중이다."""


class _Progress:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.running = False
        self.model = ""
        self.phase = ""
        self.percent = 0.0        # 현재 모델 진행률 0~100
        self.overall = 0.0        # 전체 진행률 0~100
        self.done: list[str] = []
        self.error = ""

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "running": self.running,
                "model": self.model,
                "phase": self.phase,
                "percent": round(self.percent, 1),
                "overall": round(self.overall, 1),
                "done": list(self.done),
                "error": self.error,
            }


_progress = _Progress()


def _ollama_models() -> tuple[bool, set[str]]:
    """(Ollama 응답 여부, 설치된 모델 이름 집합)."""
    try:
        response = requests.get(f"{config.OLLAMA_BASE_URL}/api/tags", timeout=5)
        response.raise_for_status()
    except requests.exceptions.RequestException:
        return False, set()

    names = set()
    for model in response.json().get("models", []):
        name = str(model.get("name", ""))
        if name:
            names.add(name)
            names.add(name.split(":")[0])  # 태그 없이 비교할 때를 위해
    return True, names


def _plan_with_presence(installed: set[str]) -> list[dict]:
    return [{**entry, "present": entry["name"] in installed} for entry in MODEL_PLAN]


def status() -> dict:
    """앱이 쓸 수 있는 상태인가? FE 준비 화면이 이 값 하나로 그려진다."""
    running, installed = _ollama_models()
    models = _plan_with_presence(installed)
    missing = [m["name"] for m in models if m["required"] and not m["present"]]

    try:
        from ..rag.search import index_status

        index = index_status()
    except Exception as exc:
        index = {"ready": False, "detail": f"색인 상태를 확인할 수 없습니다: {exc}"}

    return {
        "ollama": {
            "running": running,
            # PATH에서 실행 파일이 보이는지. 설치는 됐는데 꺼져 있는 경우를 구분한다.
            "binary_found": shutil.which("ollama") is not None,
            "base_url": config.OLLAMA_BASE_URL,
        },
        "models": models,
        "missing_required": missing,
        # 이 값이 True면 앱을 바로 쓸 수 있다 (색인은 폴더 선택 시 만들어진다).
        "ready": running and not missing,
        "download": _progress.snapshot(),
        "index": index,
    }


def _pull_one(name: str, index: int, total_models: int) -> None:
    """모델 1개를 받는다. Ollama가 진행률을 스트리밍으로 준다."""
    with _progress.lock:
        _progress.model = name
        _progress.percent = 0.0
        _progress.phase = "연결 중"

    layers: dict[str, tuple[int, int]] = {}  # digest -> (완료, 전체)

    with requests.post(f"{config.OLLAMA_BASE_URL}/api/pull",
                       json={"model": name, "stream": True},
                       stream=True, timeout=_PULL_TIMEOUT) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            import json

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if event.get("error"):
                raise RuntimeError(str(event["error"]))

            digest = event.get("digest")
            if digest and event.get("total"):
                layers[digest] = (int(event.get("completed", 0)), int(event["total"]))

            downloaded = sum(done for done, _ in layers.values())
            expected = sum(size for _, size in layers.values())
            percent = (downloaded / expected * 100) if expected else 0.0

            with _progress.lock:
                _progress.phase = str(event.get("status", ""))
                _progress.percent = percent
                # 전체 진행률: 완료한 모델 수 + 현재 모델의 진행률
                _progress.overall = (index + percent / 100) / total_models * 100


def _download_worker(names: list[str]) -> None:
    try:
        for index, name in enumerate(names):
            _pull_one(name, index, len(names))
            with _progress.lock:
                _progress.done.append(name)
                _progress.percent = 100.0
                _progress.overall = (index + 1) / len(names) * 100
    except requests.exceptions.RequestException as exc:
        with _progress.lock:
            _progress.error = f"Ollama에 연결할 수 없습니다: {exc}"
    except Exception as exc:
        with _progress.lock:
            _progress.error = str(exc)
    finally:
        with _progress.lock:
            _progress.running = False
            _progress.phase = "완료" if not _progress.error else "실패"


def start_download(include_full: bool = False) -> dict:
    """없는 모델만 골라 백그라운드로 받는다. 이미 진행 중이면 DownloadBusy."""
    with _progress.lock:
        if _progress.running:
            raise DownloadBusy("이미 모델을 받는 중입니다.")

    running, installed = _ollama_models()
    if not running:
        raise RuntimeError(
            "Ollama가 실행 중이 아닙니다. Ollama를 설치·실행한 뒤 다시 시도하세요.")

    wanted = [entry for entry in MODEL_PLAN
              if entry["required"] or (include_full and entry["role"] == "generate_full")]
    names = [entry["name"] for entry in wanted if entry["name"] not in installed]

    if not names:
        return {"started": False, "detail": "이미 모든 모델이 준비돼 있습니다.", "models": []}

    with _progress.lock:
        _progress.reset()
        _progress.running = True
        _progress.model = names[0]
        _progress.phase = "시작"

    threading.Thread(target=_download_worker, args=(names,),
                     name="model-download", daemon=True).start()
    return {"started": True, "models": names}
