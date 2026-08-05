"""첫 실행 준비 API 테스트 — Ollama를 가짜로 주입해 실제 다운로드 없이 검증한다."""

import json

import pytest

from app.setup import provision


class FakeResponse:
    def __init__(self, payload=None, lines=None, status=200):
        self._payload = payload or {}
        self._lines = lines or []
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload

    def iter_lines(self):
        for line in self._lines:
            yield json.dumps(line).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture(autouse=True)
def clean_progress(tmp_path, monkeypatch):
    # 사용자 선택(settings.json)이 실제 설정 폴더를 오염시키지 않게 한다
    from app.core import config, settings

    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(settings, "_cache", None)
    # 준비 상태 판정은 임베딩을 실제로 한 번 해 본다. 테스트에는 Ollama가 없으므로
    # 기본은 "잘 돈다"로 두고, 안 도는 경우는 해당 테스트가 직접 뒤집는다.
    monkeypatch.setattr(provision, "embed_health",
                        lambda: {"usable": True, "detail": "", "model": "test-embed"})
    provision._progress.reset()
    provision.reset_embed_health()
    yield
    provision._progress.reset()
    provision.reset_embed_health()


def required_names():
    """준비 완료로 판정되려면 있어야 하는 모델 — 임베딩 + 생성 모델 하나."""
    from app.core import config

    return [config.OLLAMA_EMBED_MODEL, config.OLLAMA_GENERATE_MODEL_SLIM]


def fake_tags(monkeypatch, names):
    payload = {"models": [{"name": name} for name in names]}
    monkeypatch.setattr(provision.requests, "get",
                        lambda *a, **k: FakeResponse(payload))


def ollama_down(monkeypatch):
    def refuse(*args, **kwargs):
        raise provision.requests.exceptions.ConnectionError("연결 거부")

    monkeypatch.setattr(provision.requests, "get", refuse)
    monkeypatch.setattr(provision.requests, "post", refuse)


class TestStatus:
    def test_ollama가_꺼져_있으면_준비_안_됨(self, monkeypatch):
        ollama_down(monkeypatch)
        state = provision.status()
        assert state["ready"] is False
        assert state["ollama"]["running"] is False
        assert len(state["missing_required"]) == 2  # 임베딩 + slim

    def test_필수_모델이_다_있으면_준비_완료(self, monkeypatch):
        fake_tags(monkeypatch, required_names())
        state = provision.status()
        assert state["ready"] is True
        assert state["missing_required"] == []

    def test_표준_모델은_없어도_준비_완료(self, monkeypatch):
        """생성 모델은 하나만 있으면 된다 — 나머지는 선택지지 필수가 아니다."""
        fake_tags(monkeypatch, required_names())
        state = provision.status()
        standard = [m for m in state["models"] if m["tier"] == "standard"][0]
        assert standard["present"] is False and standard["required"] is False
        assert state["ready"] is True

    def test_사양에_맞는_모델을_추천한다(self, monkeypatch):
        from app.core import config

        fake_tags(monkeypatch, [])
        monkeypatch.setattr(provision, "detect_hardware",
                            lambda: {"has_usable_gpu": True, "vram_gb": 8.0})
        assert provision.status()["recommendation"]["generate_model"] == \
            config.OLLAMA_GENERATE_MODEL

        monkeypatch.setattr(provision, "detect_hardware",
                            lambda: {"has_usable_gpu": False, "gpu_name": ""})
        assert provision.status()["recommendation"]["generate_model"] == \
            config.OLLAMA_GENERATE_MODEL_SLIM


class TestDownload:
    def test_ollama가_꺼져_있으면_거부한다(self, monkeypatch):
        ollama_down(monkeypatch)
        with pytest.raises(RuntimeError):
            provision.start_download()

    def test_이미_있으면_받지_않는다(self, monkeypatch):
        fake_tags(monkeypatch, required_names())
        monkeypatch.setattr(provision, "detect_hardware",
                            lambda: {"has_usable_gpu": False})
        result = provision.start_download()
        assert result["started"] is False and result["models"] == []

    def test_없는_것만_골라_받는다(self, monkeypatch):
        from app.core import config

        fake_tags(monkeypatch, [config.OLLAMA_EMBED_MODEL])
        monkeypatch.setattr(provision, "detect_hardware", lambda: {"has_usable_gpu": False})
        monkeypatch.setattr(provision, "_download_worker", lambda names: None)

        result = provision.start_download()
        assert result["models"] == [config.OLLAMA_GENERATE_MODEL_SLIM]

    def test_고른_모델을_받고_그것을_사용_모델로_삼는다(self, monkeypatch):
        from app.core import config, settings

        fake_tags(monkeypatch, [])
        monkeypatch.setattr(provision, "detect_hardware", lambda: {"has_usable_gpu": False})
        monkeypatch.setattr(provision, "_download_worker", lambda names: None)
        result = provision.start_download(models=[config.OLLAMA_GENERATE_MODEL])

        # 고른 것은 표준 모델이지만 경량 모델도 함께 받는다 — 표준 모델이 이 PC에서
        # 안 돌 때 물러설 곳이 없으면 파일명 추천 기능이 통째로 죽는다.
        assert result["models"] == [config.OLLAMA_EMBED_MODEL,
                                    config.OLLAMA_GENERATE_MODEL_SLIM,
                                    config.OLLAMA_GENERATE_MODEL]
        assert settings.generate_model() == config.OLLAMA_GENERATE_MODEL

    def test_목록에_없는_모델은_거부한다(self, monkeypatch):
        fake_tags(monkeypatch, [])
        with pytest.raises(ValueError):
            provision.start_download(models=["llama3:70b"])
        with pytest.raises(ValueError):
            provision.select_model("llama3:70b")

    def test_진행_중이면_거부한다(self, monkeypatch):
        fake_tags(monkeypatch, [])
        monkeypatch.setattr(provision, "_download_worker", lambda names: None)
        provision.start_download()
        with pytest.raises(provision.DownloadBusy):
            provision.start_download()

    def test_진행률을_레이어_합으로_계산한다(self, monkeypatch):
        monkeypatch.setattr(provision.requests, "post", lambda *a, **k: FakeResponse(
            lines=[
                {"status": "pulling manifest"},
                {"status": "downloading", "digest": "a", "total": 100, "completed": 50},
                {"status": "downloading", "digest": "b", "total": 100, "completed": 100},
            ]))
        provision._pull_one("test-model", index=0, total_models=2)

        snapshot = provision._progress.snapshot()
        assert snapshot["percent"] == 75.0        # (50+100)/200
        assert snapshot["overall"] == 37.5        # 2개 중 첫 모델의 75%
        assert snapshot["model"] == "test-model"

    def test_다운로드_실패는_상태에_이유로_남는다(self, monkeypatch):
        monkeypatch.setattr(provision.requests, "post", lambda *a, **k: FakeResponse(
            lines=[{"error": "model not found"}]))
        provision._download_worker(["없는모델"])

        snapshot = provision._progress.snapshot()
        assert snapshot["running"] is False
        assert "model not found" in snapshot["error"]


class TestApi:
    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient

        from app import create_app
        return TestClient(create_app())

    def test_상태_조회(self, client, monkeypatch):
        ollama_down(monkeypatch)
        body = client.get("/setup/status").json()
        assert body["ready"] is False
        assert "models" in body and len(body["models"]) == 3

    def test_ollama_없이_다운로드_요청하면_503(self, client, monkeypatch):
        ollama_down(monkeypatch)
        response = client.post("/setup/models")
        assert response.status_code == 503

    def test_다운로드_시작은_202(self, client, monkeypatch):
        fake_tags(monkeypatch, [])
        monkeypatch.setattr(provision, "_download_worker", lambda names: None)
        response = client.post("/setup/models")
        assert response.status_code == 202
        assert response.json()["started"] is True


class TestEmbedModelMustActuallyRun:
    """이름이 목록에 있다고 그 PC에서 도는 것은 아니다.

    배포본에서 실제로 겪은 상황이다. `ollama pull`은 레지스트리에서 파일을
    받아 오기만 해서, 낡은 실행기는 pull에 성공하고 `/api/embed`만 500으로 죽는다.
    이름만 보고 "준비 완료"를 통과시키면 사용자는 폴더를 고른 뒤에야 알게 된다.
    """

    def test_모델이_있어도_안_돌면_준비_완료가_아니다(self, monkeypatch):
        fake_tags(monkeypatch, required_names())
        monkeypatch.setattr(provision, "detect_hardware", lambda: {"has_usable_gpu": False})
        monkeypatch.setattr(provision, "embed_health", lambda: {
            "usable": False,
            "detail": "설치된 Ollama가 검색 모델을 실행하지 못합니다.",
            "model": "qwen3-embedding:0.6b",
        })

        status = provision.status()

        assert status["ready"] is False
        assert status["embed"]["usable"] is False
        assert "실행하지 못합니다" in status["embed"]["detail"]

    def test_안_도는_상태면_받을_게_없어도_확인_작업을_건다(self, monkeypatch):
        # 여기서 "이미 다 준비됨"으로 돌려보내면, 검색이 죽은 채로 굳는다.
        fake_tags(monkeypatch, required_names())
        monkeypatch.setattr(provision, "detect_hardware", lambda: {"has_usable_gpu": False})
        monkeypatch.setattr(provision, "embed_health",
                            lambda: {"usable": False, "detail": "못 씀", "model": "m"})
        monkeypatch.setattr(provision.threading, "Thread",
                            lambda *a, **k: type("T", (), {"start": lambda self: None})())

        result = provision.start_download()

        assert result["started"] is True
        assert result["models"] == []  # 받을 것은 없고 확인·교체만 돈다


class TestModelPlan:
    """사양에 맞는 구성을 받되, 경량 모델은 사양과 무관하게 항상 받는다."""

    def test_고사양이면_경량_모델도_함께_받는다(self):
        from app.core import config

        plan = provision.plan_models({"has_usable_gpu": True, "vram_gb": 8.0})

        # 예전에는 고사양 PC에 표준 모델만 받게 해 놔서, 표준 모델이 그 PC에서
        # 안 도는 순간 사용자에게 남는 선택지가 하나도 없었다.
        assert plan == [config.OLLAMA_EMBED_MODEL,
                        config.OLLAMA_GENERATE_MODEL_SLIM,
                        config.OLLAMA_GENERATE_MODEL]

    def test_저사양이면_표준_모델은_받지_않는다(self):
        from app.core import config

        plan = provision.plan_models({"has_usable_gpu": False})

        assert plan == [config.OLLAMA_EMBED_MODEL, config.OLLAMA_GENERATE_MODEL_SLIM]
        assert config.OLLAMA_GENERATE_MODEL not in plan  # 4.8GB, GPU 없이 파일당 80초

    def test_고사양_기본_다운로드는_세_개_전부(self, monkeypatch):
        from app.core import config

        fake_tags(monkeypatch, [])
        monkeypatch.setattr(provision, "detect_hardware",
                            lambda: {"has_usable_gpu": True, "vram_gb": 8.0})
        monkeypatch.setattr(provision, "_download_worker", lambda names: None)

        assert provision.start_download()["models"] == [
            config.OLLAMA_EMBED_MODEL,
            config.OLLAMA_GENERATE_MODEL_SLIM,
            config.OLLAMA_GENERATE_MODEL,
        ]


class TestGenerateModelFallback:
    def test_고른_모델을_못_받았으면_받아_둔_모델로_돌린다(self, monkeypatch):
        # 표준 모델 받기가 끊겨도 경량 모델이 있으면 파일명 추천은 돌아야 한다.
        from app.core import config, settings

        settings.set_generate_model(config.OLLAMA_GENERATE_MODEL)
        fake_tags(monkeypatch, [config.OLLAMA_EMBED_MODEL,
                                config.OLLAMA_GENERATE_MODEL_SLIM])

        provision._ensure_generate_model()

        assert settings.generate_model() == config.OLLAMA_GENERATE_MODEL_SLIM

    def test_받아_둔_모델이면_건드리지_않는다(self, monkeypatch):
        from app.core import config, settings

        settings.set_generate_model(config.OLLAMA_GENERATE_MODEL)
        fake_tags(monkeypatch, [config.OLLAMA_GENERATE_MODEL,
                                config.OLLAMA_GENERATE_MODEL_SLIM])

        provision._ensure_generate_model()

        assert settings.generate_model() == config.OLLAMA_GENERATE_MODEL


class TestVerifyEmbedModel:
    def test_기본_모델이_안_돌면_예비_모델을_받아_갈아탄다(self, monkeypatch):
        from app.core import config, settings
        from app.rag import embedding

        fallback = config.OLLAMA_EMBED_FALLBACKS[0]
        pulled = []

        monkeypatch.setattr(provision, "_pull_one",
                            lambda name, i, n: pulled.append(name))
        monkeypatch.setattr(embedding, "installed_models",
                            lambda: {config.OLLAMA_EMBED_MODEL})
        monkeypatch.setattr(embedding, "probe", lambda model: (
            (False, "메모리가 모자랍니다", embedding.FAILURE_MEMORY)
            if model == config.OLLAMA_EMBED_MODEL else (True, "", "")))

        provision._verify_embed_model()

        assert pulled == [fallback]
        assert settings.embed_model() == fallback
        assert not provision._progress.error

    def test_기본_모델이_돌면_아무것도_받지_않는다(self, monkeypatch):
        from app.core import config, settings
        from app.rag import embedding

        pulled = []
        monkeypatch.setattr(provision, "_pull_one", lambda name, i, n: pulled.append(name))
        monkeypatch.setattr(embedding, "installed_models",
                            lambda: {config.OLLAMA_EMBED_MODEL})
        monkeypatch.setattr(embedding, "probe", lambda model: (True, "", ""))

        provision._verify_embed_model()

        assert pulled == []
        assert settings.embed_model() == config.OLLAMA_EMBED_MODEL

    def test_예비_모델도_안_되면_이유를_남긴다(self, monkeypatch):
        from app.rag import embedding

        monkeypatch.setattr(provision, "_pull_one", lambda name, i, n: None)
        monkeypatch.setattr(embedding, "installed_models", lambda: set())
        monkeypatch.setattr(embedding, "probe", lambda model: (
            False, "메모리가 부족합니다", embedding.FAILURE_MEMORY))

        provision._verify_embed_model()

        assert "메모리가 부족합니다" in provision._progress.error

    def test_실행기가_깨졌으면_예비_모델을_받지_않고_갈래를_남긴다(self, monkeypatch):
        """남의 PC에서 실제로 본 상태 — Ollama는 떠 있는데 llama-server가 없다.

        이때 예비 모델을 받아 봐야 똑같이 죽는다. 받지 않고, 화면이 "Ollama
        다시 설치"를 띄울 수 있도록 갈래(runtime)를 남겨야 한다.
        """
        from app.core import config
        from app.rag import embedding

        pulled = []
        monkeypatch.setattr(provision, "_pull_one",
                            lambda name, i, n: pulled.append(name))
        monkeypatch.setattr(embedding, "installed_models",
                            lambda: {config.OLLAMA_EMBED_MODEL}
                            | set(config.OLLAMA_EMBED_FALLBACKS))
        monkeypatch.setattr(embedding, "probe", lambda model: (
            False, "Ollama가 이 PC에서 모델을 실행하지 못합니다",
            embedding.FAILURE_RUNTIME))

        provision._verify_embed_model()

        assert pulled == []
        assert provision._progress.error_kind == embedding.FAILURE_RUNTIME
        assert provision._progress.snapshot()["error_kind"] == "runtime"
