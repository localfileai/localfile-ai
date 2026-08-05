"""임베딩 모델 진단·교체 테스트. Ollama 없이 응답만 흉내 내서 돈다.

배경: 배포본에서 `/api/embed`가 500을 냈는데 화면에는 "500 Server Error"만
남았다. Ollama는 실패 이유를 본문에 담아 주는데 `raise_for_status()`가 그걸
삼켰기 때문이다. 그리고 `ollama pull`이 성공했다는 사실은 그 PC에서 모델이
**돈다**는 뜻이 아니라서, 이름만 보고 준비됐다고 판단하면 안 된다.
"""

import pytest

from app.core import config
from app.rag import embedding


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        if self._payload is None:
            raise ValueError("본문이 JSON이 아님")
        return self._payload


@pytest.fixture(autouse=True)
def clean_state(monkeypatch, tmp_path):
    """확인 결과 캐시와 설정 파일을 테스트마다 초기화한다."""
    from app.core import settings

    monkeypatch.setattr(settings, "_cache", {}, raising=False)
    monkeypatch.setattr(settings, "_path", lambda: tmp_path / "settings.json")
    embedding.forget_verified_model()
    yield
    embedding.forget_verified_model()


class TestErrorMessage:
    """500의 진짜 이유가 사용자에게 닿아야 한다."""

    def test_메모리_부족은_메모리_부족이라고_말한다(self, monkeypatch):
        monkeypatch.setattr(embedding._session, "post", lambda *a, **k: FakeResponse(
            500, {"error": "model requires more system memory (5.6 GiB) than is available"}))

        with pytest.raises(embedding.EmbeddingUnavailable) as caught:
            embedding._embed("qwen3-embedding:0.6b", ["문서"], timeout=5)

        assert "메모리가 부족" in str(caught.value)
        assert "5.6 GiB" in str(caught.value)  # Ollama 원문도 남긴다

    def test_실행기가_낡으면_업데이트를_안내한다(self, monkeypatch):
        monkeypatch.setattr(embedding._session, "post", lambda *a, **k: FakeResponse(
            500, {"error": "unable to load model: unknown model architecture 'qwen3'"}))

        with pytest.raises(embedding.EmbeddingUnavailable) as caught:
            embedding._embed("qwen3-embedding:0.6b", ["문서"], timeout=5)

        message = str(caught.value)
        assert "Ollama를 최신 버전으로" in message
        assert "ollama.com/download" in message

    def test_이유를_모를_때도_원문을_남긴다(self, monkeypatch):
        monkeypatch.setattr(embedding._session, "post", lambda *a, **k: FakeResponse(
            500, {"error": "처음 보는 오류"}))

        with pytest.raises(embedding.EmbeddingUnavailable) as caught:
            embedding._embed("m", ["문서"], timeout=5)

        assert "처음 보는 오류" in str(caught.value)

    def test_빈_응답도_실패로_본다(self, monkeypatch):
        # 200인데 벡터가 없으면 조용히 넘어가면 안 된다 — 색인이 통째로 비게 된다.
        monkeypatch.setattr(embedding._session, "post",
                            lambda *a, **k: FakeResponse(200, {"embeddings": []}))

        with pytest.raises(embedding.EmbeddingUnavailable):
            embedding._embed("m", ["문서"], timeout=5)


class TestLegacyEndpoint:
    def test_구버전_Ollama는_단건_엔드포인트로_돈다(self, monkeypatch):
        # /api/embed(묶음)는 Ollama 0.3부터다. 그 전 버전은 404를 준다.
        calls = []

        def fake_post(url, **kwargs):
            calls.append(url)
            if url.endswith("/api/embed"):
                return FakeResponse(404, {"error": "not found"})
            return FakeResponse(200, {"embedding": [0.1, 0.2]})

        monkeypatch.setattr(embedding._session, "post", fake_post)

        vectors = embedding._embed("m", ["문서1", "문서2"], timeout=5)

        assert vectors == [[0.1, 0.2], [0.1, 0.2]]
        assert calls.count(f"{embedding.OLLAMA_BASE_URL}/api/embeddings") == 2


class TestEnsureUsableModel:
    """이름이 목록에 있는 것과 그 PC에서 도는 것은 다른 문제다."""

    def test_기본_모델이_돌면_그대로_쓴다(self, monkeypatch):
        monkeypatch.setattr(embedding, "installed_models",
                            lambda: {config.OLLAMA_EMBED_MODEL})
        monkeypatch.setattr(embedding, "probe", lambda model: (True, ""))

        assert embedding.ensure_usable_model() == config.OLLAMA_EMBED_MODEL

    def test_기본_모델이_안_돌면_예비_모델로_갈아탄다(self, monkeypatch):
        from app.core import settings

        fallback = config.OLLAMA_EMBED_FALLBACKS[0]
        monkeypatch.setattr(embedding, "installed_models",
                            lambda: {config.OLLAMA_EMBED_MODEL, fallback})
        monkeypatch.setattr(embedding, "probe", lambda model: (
            (False, "설치된 Ollama가 실행하지 못합니다") if model == config.OLLAMA_EMBED_MODEL
            else (True, "")))

        assert embedding.ensure_usable_model() == fallback
        # 색인과 검색이 같은 모델을 써야 하므로 결정이 남아야 한다.
        assert settings.embed_model() == fallback

    def test_설치되지_않은_모델은_시도하지_않는다(self, monkeypatch):
        probed = []
        monkeypatch.setattr(embedding, "installed_models", lambda: set())
        monkeypatch.setattr(embedding, "probe",
                            lambda model: probed.append(model) or (True, ""))

        with pytest.raises(embedding.EmbeddingUnavailable) as caught:
            embedding.ensure_usable_model()

        assert probed == []
        assert "설치되어 있지 않습니다" in str(caught.value)

    def test_전부_안_되면_첫_이유를_올린다(self, monkeypatch):
        monkeypatch.setattr(embedding, "installed_models",
                            lambda: {config.OLLAMA_EMBED_MODEL} | set(
                                config.OLLAMA_EMBED_FALLBACKS))
        monkeypatch.setattr(embedding, "probe",
                            lambda model: (False, f"{model} 못 씀"))

        with pytest.raises(embedding.EmbeddingUnavailable) as caught:
            embedding.ensure_usable_model()

        assert config.OLLAMA_EMBED_MODEL in str(caught.value)

    def test_한_번_확인한_모델은_다시_확인하지_않는다(self, monkeypatch):
        # 확인 자체가 임베딩 1회다. 색인 배치마다 부르면 그만큼 느려진다.
        count = {"n": 0}

        def counting_probe(model):
            count["n"] += 1
            return True, ""

        monkeypatch.setattr(embedding, "installed_models",
                            lambda: {config.OLLAMA_EMBED_MODEL})
        monkeypatch.setattr(embedding, "probe", counting_probe)

        embedding.ensure_usable_model()
        embedding.ensure_usable_model()
        assert count["n"] == 1
