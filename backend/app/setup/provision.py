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
import time

import requests

from ..core import config, settings
from .hardware import detect as detect_hardware
from .hardware import summary as hardware_summary

# 고를 수 있는 모델 목록. 전부 3주차에 같은 평가셋으로 실측한 것들이다
# (docs/decisions/0002-model-selection.md). 검증하지 않은 모델은 여기 넣지 않는다 —
# 고르게 해 놓고 성능을 보장 못 하면 선택지가 아니라 함정이다.
#
# `license` / `commercial`은 유료화를 검토하면서 넣었다 (ADR-0004). 모델마다
# 조건이 다르고, 그 사실이 코드 어디에도 안 적혀 있으면 나중에 아무도 모른 채
# 위반한다. exaone3.5는 비상업(NC) 조건이라 돈을 받는 순간 별도 계약이 필요하다.
MODEL_CATALOG: list[dict] = [
    {
        "name": config.OLLAMA_EMBED_MODEL,
        "role": "embed",
        "tier": "",
        "label": "검색·분류 엔진",
        "approx_gb": 0.6,
        "purpose": "문서를 이해해 검색하고 분류합니다. 앱의 핵심이라 반드시 필요합니다.",
        "detail": "GPU가 없어도 문서 1건당 0.2초 수준으로 동작합니다.",
        "license": "Apache-2.0",
        "commercial": True,
    },
    {
        "name": config.OLLAMA_GENERATE_MODEL_SLIM,
        "role": "generate",
        "tier": "light",
        "label": "파일명 추천 · 경량",
        "approx_gb": 1.6,
        "purpose": "추천 파일명을 만듭니다. 그래픽카드가 없는 PC를 위한 선택입니다.",
        "detail": "파일명 품질 84%. GPU 없이 파일당 약 13초.",
        "license": "EXAONE AI Model License 1.1 (비상업)",
        "commercial": False,
    },
    {
        "name": config.OLLAMA_GENERATE_MODEL,
        "role": "generate",
        "tier": "standard",
        "label": "파일명 추천 · 표준",
        "approx_gb": 4.8,
        "purpose": "추천 파일명을 만듭니다. 그래픽카드가 있으면 이쪽이 빠르고 정확합니다.",
        "detail": "GPU에서 파일당 약 4초. GPU가 없으면 파일당 80초가 넘어 권하지 않습니다.",
        "license": "EXAONE AI Model License 1.1 (비상업)",
        "commercial": False,
    },
]

# 이전 이름. 외부에서 참조하던 곳이 있어 남겨 둔다.
MODEL_PLAN = MODEL_CATALOG


def recommended_generate_model(hardware: dict) -> str:
    """이 PC에 권하는 파일명 추천 모델.

    기준은 하나다 — **쓸 만한 GPU가 있는가**. 3주차 실측에서 7.8b는 GPU 4.3초 /
    CPU 81초로 갈렸다. GPU가 없으면 표준 모델은 받아 봐야 못 쓴다.
    """
    if hardware.get("has_usable_gpu"):
        return config.OLLAMA_GENERATE_MODEL
    return config.OLLAMA_GENERATE_MODEL_SLIM


def recommendation_reason(hardware: dict) -> str:
    """왜 그 모델을 권하는지 사용자에게 한 줄로."""
    if hardware.get("has_usable_gpu"):
        vram = hardware.get("vram_gb") or 0
        return (f"그래픽카드({vram:g}GB)가 있어 표준 모델을 권합니다. "
                f"경량 모델도 함께 받아 둡니다 (표준 모델이 버거울 때 대신 씁니다).")
    if hardware.get("gpu_name"):
        return "그래픽카드 메모리가 부족해 경량 모델만 받습니다."
    return "그래픽카드가 없어 경량 모델만 받습니다. 표준 모델은 너무 느립니다."


def plan_models(hardware: dict) -> list[str]:
    """이 PC에 받아 둘 모델 구성. 사용자가 따로 고르지 않으면 이대로 받는다.

    경량 모델(2.4b)은 **사양과 무관하게 항상 받는다.** 표준 모델(7.8b)은 GPU
    메모리가 모자라면 로딩부터 실패하거나 파일당 80초가 넘어가고, 그때 물러설
    곳이 없으면 파일명 추천 기능 자체가 죽는다. 1.6GB로 그 위험을 없앤다.
    예전에는 고사양 PC에 표준 모델만 받게 해 놔서, 표준 모델이 안 도는 순간
    사용자에게 남는 선택지가 하나도 없었다.
    """
    plan = [config.OLLAMA_EMBED_MODEL, config.OLLAMA_GENERATE_MODEL_SLIM]
    if hardware.get("has_usable_gpu"):
        plan.append(config.OLLAMA_GENERATE_MODEL)
    return plan

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
        # 실패 갈래(embedding.FAILURE_*). 화면이 "그래서 뭘 눌러야 하나"를 정한다 —
        # runtime이면 모델을 더 받아 봐야 소용없고 Ollama를 다시 설치해야 한다.
        self.error_kind = ""

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
                "error_kind": self.error_kind,
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


# 임베딩 실동작 확인 결과 캐시. 확인 한 번이 임베딩 1회라, 상태를 폴링할 때마다
# 새로 재면 준비 화면이 그 자체로 느려진다.
_health_lock = threading.Lock()
_health: dict = {"checked_at": 0.0, "usable": False, "detail": "", "model": "",
                 "kind": ""}
HEALTH_TTL_SEC = 60.0


def reset_embed_health() -> None:
    """확인 결과를 버린다. 모델을 새로 받은 뒤에 부른다."""
    with _health_lock:
        _health["checked_at"] = 0.0


def embed_health() -> dict:
    """검색 모델이 이 PC에서 **실제로** 도는가. (캐시됨)

    이름이 `ollama list`에 있는 것과 도는 것은 다른 문제다. 이 구분이 없으면
    준비 화면은 "준비 완료"라고 하고, 사용자는 폴더를 고른 뒤에야 아무것도
    안 된다는 걸 알게 된다.
    """
    from ..rag import embedding

    now = time.monotonic()
    with _health_lock:
        if now - _health["checked_at"] < HEALTH_TTL_SEC and _health["checked_at"]:
            return dict(_health)

    try:
        model = embedding.ensure_usable_model()
        result = {"checked_at": now, "usable": True, "detail": "", "model": model,
                  "kind": ""}
    except embedding.EmbeddingUnavailable as exc:
        result = {"checked_at": now, "usable": False, "detail": str(exc),
                  "model": embedding.resolve_model(), "kind": exc.kind}

    with _health_lock:
        _health.update(result)
        return dict(result)


def status() -> dict:
    """앱이 쓸 수 있는 상태인가? FE 준비 화면이 이 값 하나로 그려진다."""
    running, installed = _ollama_models()

    hardware = detect_hardware()
    recommended = recommended_generate_model(hardware)
    planned = plan_models(hardware)
    selected = settings.generate_model()

    models = [{
        **entry,
        "present": entry["name"] in installed,
        "recommended": entry["role"] == "embed" or entry["name"] == recommended,
        # 임베딩은 선택 대상이 아니라 필수다.
        "required": entry["role"] == "embed",
        # 이 PC 구성에 포함되는가 — "한 번에 모두 설치"가 받을 목록이다.
        "planned": entry["name"] in planned,
        "selected": entry["name"] == selected,
    } for entry in MODEL_CATALOG]

    embed_missing = [m["name"] for m in models if m["role"] == "embed" and not m["present"]]
    has_generate = any(m["role"] == "generate" and m["present"] for m in models)
    # 모델이 하나도 없는 단계에서 임베딩을 시도할 필요는 없다 (실패가 뻔하다).
    health = (embed_health() if running and not embed_missing
              else {"usable": False, "detail": "", "kind": "",
                    "model": settings.embed_model()})

    try:
        from ..rag.search import index_status

        index = index_status()
    except Exception as exc:
        index = {"ready": False, "detail": f"색인 상태를 확인할 수 없습니다: {exc}"}

    from ..rag import embedding

    return {
        "ollama": {
            "running": running,
            # PATH에서 실행 파일이 보이는지. 설치는 됐는데 꺼져 있는 경우를 구분한다.
            "binary_found": shutil.which("ollama") is not None,
            "base_url": config.OLLAMA_BASE_URL,
            # 낡은 Ollama는 최신 모델을 받아도 실행하지 못한다 — 문의가 들어왔을 때
            # 제일 먼저 봐야 하는 값이라 상태에 넣어 둔다.
            "version": embedding.ollama_version(),
        },
        "hardware": {**hardware, "summary": hardware_summary(hardware)},
        "recommendation": {
            "generate_model": recommended,
            "reason": recommendation_reason(hardware),
            # 이 PC에 받아 둘 구성 전부. 고사양이면 경량 모델도 들어 있다 —
            # 표준 모델이 안 돌 때 물러설 곳이 있어야 하기 때문이다.
            "plan": planned,
            # 이번에 실제로 받아야 하는 것만.
            "pending": [name for name in planned if name not in installed],
        },
        "selected_model": selected,
        # 실제로 검색에 쓰이는 임베딩 모델. 기본 모델이 이 PC에서 안 돌아
        # 예비 모델로 갈아탄 경우 카탈로그의 이름과 달라진다.
        "active_embed_model": settings.embed_model(),
        # 이름이 목록에 있는지가 아니라 **실제로 도는지**.
        "embed": health,
        "models": models,
        "missing_required": embed_missing + ([] if has_generate else [selected]),
        # 이 값이 True면 앱을 바로 쓸 수 있다 (색인은 폴더 선택 시 만들어진다).
        # 검색 모델이 실제로 돌지 않으면 준비된 것이 아니다 — 예전에는 이름만 보고
        # 통과시켜서, 사용자가 폴더를 고른 뒤에야 아무것도 안 된다는 걸 알았다.
        "ready": running and not embed_missing and has_generate and health["usable"],
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


def _verify_embed_model() -> None:
    """받은 검색 모델이 이 PC에서 **정말 도는지** 확인하고, 안 되면 예비 모델로.

    `ollama pull`은 레지스트리에서 파일을 받아 오기만 한다. 낡은 실행기나 부족한
    메모리 때문에 못 돌아도 pull은 성공하고 목록에도 이름이 뜬다. 그 상태로
    준비 화면을 통과시키면, 사용자는 폴더를 고르고 한참 기다린 끝에 "검색할 문서가
    없습니다"만 보게 된다. 그 판정을 여기서, 사용자가 아직 화면 앞에 있을 때 한다.
    """
    from ..rag import embedding

    def fetch(name: str) -> None:
        """예비 모델이 아직 없으면 여기서 받는다 — 진행률은 그대로 화면에 흐른다."""
        with _progress.lock:
            _progress.phase = "이 PC에서 되는 검색 모델을 받는 중"
        _pull_one(name, 0, 1)

    # 기본 모델부터 다시 재 본다. 방금 받았으니 이전 확인 결과는 버린다.
    embedding.forget_verified_model()
    try:
        settings.set_embed_model(
            embedding.ensure_usable_model(force=True, pull=fetch))
    except embedding.EmbeddingUnavailable as exc:
        with _progress.lock:
            _progress.error = str(exc)
            _progress.error_kind = exc.kind


def _ensure_generate_model() -> None:
    """쓰기로 한 파일명 모델이 실제로 깔려 있는지 확인하고, 없으면 있는 것으로.

    표준 모델 받기가 중간에 끊겨도 경량 모델이 남아 있으면 파일명 추천은 계속
    돌아야 한다. 이 확인이 없으면 "설정에는 표준 모델, 디스크에는 없음" 상태로
    굳어 추천 기능만 조용히 죽는다.
    """
    installed = _ollama_models()[1]
    if settings.generate_model() in installed:
        return
    for entry in MODEL_CATALOG:
        if entry["role"] == "generate" and entry["name"] in installed:
            settings.set_generate_model(entry["name"])
            return


def _download_worker(names: list[str]) -> None:
    try:
        for index, name in enumerate(names):
            _pull_one(name, index, len(names))
            with _progress.lock:
                _progress.done.append(name)
                _progress.percent = 100.0
                _progress.overall = (index + 1) / len(names) * 100
        _ensure_generate_model()
        _verify_embed_model()
    except requests.exceptions.RequestException as exc:
        with _progress.lock:
            _progress.error = f"Ollama에 연결할 수 없습니다: {exc}"
            _progress.error_kind = "offline"
    except Exception as exc:
        with _progress.lock:
            _progress.error = str(exc)
    finally:
        # 모델 구성이 바뀌었으니 이전 확인 결과는 못 믿는다.
        reset_embed_health()
        with _progress.lock:
            _progress.running = False
            _progress.phase = "완료" if not _progress.error else "실패"


def select_model(name: str) -> str:
    """파일명 추천에 쓸 모델을 고른다. 목록에 없는 이름은 거부한다."""
    allowed = {entry["name"] for entry in MODEL_CATALOG if entry["role"] == "generate"}
    if name not in allowed:
        raise ValueError(f"고를 수 없는 모델입니다: {name}")
    settings.set_generate_model(name)
    return name


def start_download(include_full: bool = False, models: list[str] | None = None) -> dict:
    """없는 모델만 골라 백그라운드로 받는다. 이미 진행 중이면 DownloadBusy.

    models를 주면 그 목록을(임베딩은 항상 포함) 받는다. 안 주면 이 PC에
    권장되는 구성을 받는다.
    """
    with _progress.lock:
        if _progress.running:
            raise DownloadBusy("이미 모델을 받는 중입니다.")

    running, installed = _ollama_models()
    if not running:
        raise RuntimeError(
            "Ollama가 실행 중이 아닙니다. Ollama를 설치·실행한 뒤 다시 시도하세요.")

    catalog = {entry["name"]: entry for entry in MODEL_CATALOG}
    hardware = detect_hardware()
    # 이 PC의 기본 구성은 뭘 고르든 항상 깔린다. 사용자가 표준 모델을 골랐다고
    # 경량 모델을 빼면, 표준 모델이 그 PC에서 안 도는 순간 물러설 곳이 없다.
    wanted = plan_models(hardware)
    if include_full and config.OLLAMA_GENERATE_MODEL not in wanted:
        wanted.append(config.OLLAMA_GENERATE_MODEL)

    if models:
        unknown = [name for name in models if name not in catalog]
        if unknown:
            raise ValueError(f"목록에 없는 모델입니다: {', '.join(unknown)}")
        wanted += [name for name in models if name not in wanted]
        # 사용자가 직접 고른 경우 — 고른 것을 그대로 쓴다.
        use = next((name for name in models if catalog[name]["role"] == "generate"), "")
    else:
        use = config.OLLAMA_GENERATE_MODEL if include_full else \
            recommended_generate_model(hardware)

    if use:
        settings.set_generate_model(use)

    seen: set[str] = set()
    names = [name for name in wanted
             if name not in installed and not (name in seen or seen.add(name))]

    if not names:
        # 받을 것이 없어도 검색 모델이 안 돌면 그냥 돌려보내면 안 된다.
        # 그러면 "다 준비됨"이라 말하고 검색은 죽어 있는 상태가 그대로 유지된다.
        # 빈 목록으로 작업을 걸어 확인·교체(_verify_embed_model)만 돌린다.
        if embed_health()["usable"]:
            return {"started": False, "detail": "이미 모든 모델이 준비돼 있습니다.", "models": []}
        reset_embed_health()

    with _progress.lock:
        _progress.reset()
        _progress.running = True
        # 받을 것 없이 확인만 도는 경우가 있다 (이미 다 깔렸는데 안 도는 상태).
        _progress.model = names[0] if names else config.OLLAMA_EMBED_MODEL
        _progress.phase = "시작" if names else "검색 모델을 확인하는 중"

    threading.Thread(target=_download_worker, args=(names,),
                     name="model-download", daemon=True).start()
    return {"started": True, "models": names}
