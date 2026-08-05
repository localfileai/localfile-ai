"""폴더 문서 목록 API 테스트.

이 목록은 "어떤 파일이 있는가"만 답하면 된다. 예전에는 목록을 만들려고
모든 파일의 텍스트를 추출해 파일이 많은 폴더에서 화면이 멈춘 것처럼 보였다.
그래서 **하위 폴더까지 다 나오는가**와 **추출 없이 빠른가**가 핵심이다.
"""

import pytest
from fastapi.testclient import TestClient

from app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def tree(tmp_path):
    """하위 폴더가 있는 폴더를 만든다."""
    (tmp_path / "위층.pdf").write_bytes(b"%PDF-1.4 test")
    nested = tmp_path / "강의자료" / "운영체제"
    nested.mkdir(parents=True)
    (nested / "3주차.pdf").write_bytes(b"%PDF-1.4 test")
    (nested / "메모.txt").write_text("지원하지 않는 형식", encoding="utf-8")
    return tmp_path


def test_하위_폴더_문서까지_모두_나온다(client, tree):
    body = client.get("/files", params={"path": str(tree)}).json()

    names = {item["name"] for item in body["items"]}
    assert names == {"위층.pdf", "3주차.pdf"}   # txt는 지원 형식이 아니라 빠진다
    assert body["total"] == 2


def test_고른_폴더_기준_상대_위치를_알려_준다(client, tree):
    items = {item["name"]: item for item in client.get(
        "/files", params={"path": str(tree)}).json()["items"]}

    assert items["위층.pdf"]["folder"] == ""            # 바로 아래
    # 화면에서 "어느 하위 폴더에 있는지" 보여 주는 값
    assert items["3주차.pdf"]["folder"].replace("\\", "/") == "강의자료/운영체제"


def test_없는_경로는_400(client, tmp_path):
    response = client.get("/files", params={"path": str(tmp_path / "없음")})
    assert response.status_code == 400


class TestSearchScope:
    """검색은 지금 고른 폴더의 문서만 대상으로 해야 한다.

    색인 컬렉션은 하나뿐이라 여러 폴더를 오가며 쓰면 예전 폴더의 파일이
    결과에 섞였다. 색인 시 root를 함께 저장하고 질의에서 걸러 낸다.
    """

    def test_root로_거른_질의를_보낸다(self, monkeypatch):
        from app.rag import search as search_module

        captured = {}

        class FakeCollection:
            def count(self):
                return 3

            def query(self, **kwargs):
                captured.update(kwargs)
                return {"metadatas": [[]], "documents": [[]], "distances": [[]]}

        monkeypatch.setattr(search_module, "check_ollama", lambda *a, **k: (True, ""))
        monkeypatch.setattr(search_module, "_active_collection",
                            lambda: (FakeCollection(), "user"))

        search_module.search("과제", top_k=5, root="C:/Users/a/Downloads")

        assert captured["where"] == {"root": "C:/Users/a/Downloads"}

    def test_root가_없으면_전체에서_찾는다(self, monkeypatch):
        from app.rag import search as search_module

        captured = {}

        class FakeCollection:
            def count(self):
                return 3

            def query(self, **kwargs):
                captured.update(kwargs)
                return {"metadatas": [[]], "documents": [[]], "distances": [[]]}

        monkeypatch.setattr(search_module, "check_ollama", lambda *a, **k: (True, ""))
        monkeypatch.setattr(search_module, "_active_collection",
                            lambda: (FakeCollection(), "user"))

        search_module.search("과제", top_k=5)

        assert "where" not in captured
