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
def clean_progress():
    provision._progress.reset()
    yield
    provision._progress.reset()


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
        required = [m["name"] for m in provision.MODEL_PLAN if m["required"]]
        fake_tags(monkeypatch, required)
        state = provision.status()
        assert state["ready"] is True
        assert state["missing_required"] == []

    def test_고품질_모델은_없어도_준비_완료(self, monkeypatch):
        """경량 기본 구성 — 7.8b는 선택 업그레이드라 준비 판정을 막지 않는다."""
        required = [m["name"] for m in provision.MODEL_PLAN if m["required"]]
        fake_tags(monkeypatch, required)
        state = provision.status()
        full = [m for m in state["models"] if m["role"] == "generate_full"][0]
        assert full["present"] is False and full["required"] is False
        assert state["ready"] is True


class TestDownload:
    def test_ollama가_꺼져_있으면_거부한다(self, monkeypatch):
        ollama_down(monkeypatch)
        with pytest.raises(RuntimeError):
            provision.start_download()

    def test_이미_있으면_받지_않는다(self, monkeypatch):
        required = [m["name"] for m in provision.MODEL_PLAN if m["required"]]
        fake_tags(monkeypatch, required)
        result = provision.start_download()
        assert result["started"] is False and result["models"] == []

    def test_없는_것만_골라_받는다(self, monkeypatch):
        embed = provision.MODEL_PLAN[0]["name"]
        slim = provision.MODEL_PLAN[1]["name"]
        fake_tags(monkeypatch, [embed])
        monkeypatch.setattr(provision, "_download_worker", lambda names: None)

        result = provision.start_download()
        assert result["models"] == [slim]

    def test_고품질_포함_선택시_7_8b도_받는다(self, monkeypatch):
        fake_tags(monkeypatch, [])
        monkeypatch.setattr(provision, "_download_worker", lambda names: None)
        result = provision.start_download(include_full=True)
        assert len(result["models"]) == 3

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
