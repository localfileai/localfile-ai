"""사용자 폴더 색인기·검색 소스 전환 테스트. ChromaDB·Ollama 없이 돈다."""

import time

import pytest
from fastapi.testclient import TestClient

from app import create_app
from app.rag import indexer, search as search_module


class FakeUserCollection:
    """user_documents 컬렉션 흉내 — upsert/get/count/query만."""

    def __init__(self):
        self.rows: dict = {}  # id -> (document, metadata)

    def upsert(self, ids, documents, metadatas):
        for id_, doc, meta in zip(ids, documents, metadatas):
            self.rows[id_] = (doc, meta)

    def get(self, ids):
        known = [i for i in ids if i in self.rows]
        return {"ids": known, "metadatas": [self.rows[i][1] for i in known]}

    def count(self):
        return len(self.rows)

    def query(self, query_texts, n_results):
        picked = list(self.rows.items())[:n_results]
        return {
            "metadatas": [[meta for _, (_, meta) in picked]],
            "documents": [[doc for _, (doc, _) in picked]],
            "distances": [[0.2 for _ in picked]],
        }


@pytest.fixture()
def fake_collection(monkeypatch):
    collection = FakeUserCollection()
    monkeypatch.setattr(indexer, "user_collection", lambda create=False: collection)
    monkeypatch.setattr(search_module, "user_collection", lambda create=False: collection)
    return collection


def wait_done(timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not indexer.status()["running"]:
            return indexer.status()
        time.sleep(0.02)
    raise AssertionError("색인이 끝나지 않음")


def extracted(path, name, text="본문 텍스트", error=""):
    return {"path": path, "name": name, "extension": ".pdf",
            "raw_text": text, "normalized_text": text, "preview_text": text,
            "error": error}


class TestIndexer:
    def test_색인_후_증분_스킵(self, fake_collection, monkeypatch, tmp_path):
        file_a = tmp_path / "최종.pdf"
        file_a.write_bytes(b"x")
        monkeypatch.setattr(indexer, "extract_from_path",
                            lambda path, max_chars: [extracted(str(file_a), "최종.pdf")])

        indexer.start(str(tmp_path))
        state = wait_done()
        assert state["done"] == 1 and state["skipped"] == 0 and not state["error"]
        meta = fake_collection.rows[str(file_a)][1]
        assert meta["source"] == "user"
        assert meta["current_path"] == str(file_a)
        assert isinstance(meta["mtime_us"], int)  # float은 Chroma 왕복에서 정밀도가 깨진다

        # 같은 파일을 다시 색인하면 mtime이 같아 건너뛴다.
        indexer.start(str(tmp_path))
        state = wait_done()
        assert state["done"] == 0 and state["skipped"] == 1

    def test_최근_수정_파일부터_색인(self, fake_collection, monkeypatch, tmp_path):
        import os

        old = tmp_path / "옛날자료.pdf"
        new = tmp_path / "어제받은거.pdf"
        old.write_bytes(b"x")
        new.write_bytes(b"x")
        os.utime(old, (1_000_000, 1_000_000))          # 아주 오래된 파일
        monkeypatch.setattr(indexer, "extract_from_path", lambda path, max_chars: [
            extracted(str(old), "옛날자료.pdf"),        # 추출은 경로순 = 옛날 것이 먼저
            extracted(str(new), "어제받은거.pdf"),
        ])
        indexer.start(str(tmp_path))
        wait_done()
        # 색인 순서는 최근 파일이 먼저여야 한다 (dict는 삽입 순서를 보존한다).
        assert list(fake_collection.rows)[0] == str(new)

        # max_files에 걸려도 최신 파일이 우선 포함된다.
        fake_collection.rows.clear()
        indexer.start(str(tmp_path), max_files=1)
        state = wait_done()
        assert list(fake_collection.rows) == [str(new)]
        assert state["total"] == 1

    def test_임베딩_텍스트는_상한까지만(self, fake_collection, monkeypatch, tmp_path):
        from app.core import config

        file_a = tmp_path / "긴문서.pdf"
        file_a.write_bytes(b"x")
        monkeypatch.setattr(indexer, "extract_from_path", lambda path, max_chars: [
            extracted(str(file_a), "긴문서.pdf", text="가" * 1500)])
        indexer.start(str(tmp_path))
        wait_done()
        stored_text = fake_collection.rows[str(file_a)][0]
        assert len(stored_text) == config.INDEX_EMBED_MAX_CHARS

    def test_실패_파일은_기록하고_계속(self, fake_collection, monkeypatch, tmp_path):
        good = tmp_path / "a.pdf"
        good.write_bytes(b"x")
        monkeypatch.setattr(indexer, "extract_from_path", lambda path, max_chars: [
            extracted(str(good), "a.pdf"),
            extracted(str(tmp_path / "스캔.pdf"), "스캔.pdf", text="", error="텍스트 레이어 없음"),
        ])
        indexer.start(str(tmp_path))
        state = wait_done()
        assert state["done"] == 1
        assert state["failed"][0]["reason"].startswith("텍스트 레이어")

    def test_없는_경로는_시작_전에_거부(self, fake_collection):
        with pytest.raises(FileNotFoundError):
            indexer.start("/없는/경로/어딘가")


class TestIndexRoute:
    @pytest.fixture()
    def client(self):
        return TestClient(create_app())

    def test_색인_시작과_상태(self, client, fake_collection, monkeypatch, tmp_path):
        (tmp_path / "a.pdf").write_bytes(b"x")
        monkeypatch.setattr(indexer, "extract_from_path",
                            lambda path, max_chars: [extracted(str(tmp_path / "a.pdf"), "a.pdf")])
        response = client.post("/index", json={"path": str(tmp_path)})
        assert response.status_code == 202
        wait_done()
        status = client.get("/index/status").json()
        assert status["done"] == 1

    def test_없는_경로는_400(self, client, fake_collection):
        response = client.post("/index", json={"path": "C:/없는/폴더"})
        assert response.status_code == 400


class TestSearchSourceSwitch:
    def test_사용자_색인이_있으면_검색은_user_소스(self, fake_collection, monkeypatch, tmp_path):
        real = tmp_path / "진짜문서.pdf"
        real.write_bytes(b"x")
        fake_collection.upsert(
            ids=[str(real)],
            documents=["운영체제 스케줄링 정리"],
            metadatas=[{"source": "user", "current_name": "진짜문서.pdf",
                        "current_path": str(real), "extension": "pdf", "mtime": 1.0}])
        monkeypatch.setattr(search_module, "check_ollama", lambda *a, **k: (True, ""))

        response = search_module.search("스케줄링")
        assert response.total_hits == 1
        # 사용자 색인의 절대 경로가 그대로 FileRef.path로 나와야 한다.
        assert response.hits[0].file.path == str(real)

        status = search_module.index_status()
        assert status["source"] == "user"
        assert status["user_documents"] == 1

    def test_사용자_색인이_없으면_dataset_소스(self, monkeypatch):
        monkeypatch.setattr(search_module, "user_collection", lambda create=False: None)
        monkeypatch.setattr(search_module, "check_ollama", lambda *a, **k: (True, ""))

        class FakeDataset:
            def count(self):
                return 0
        monkeypatch.setattr(search_module, "_collection", lambda: FakeDataset())

        status = search_module.index_status()
        assert status["source"] == "dataset"
