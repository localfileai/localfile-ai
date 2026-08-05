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

    def get(self, ids=None, include=None, limit=None):
        # ids 없이 부르면 전체를 준다 — 검색의 파일명 대조가 이렇게 읽는다.
        known = [i for i in ids if i in self.rows] if ids is not None else list(self.rows)
        known = known[:limit] if limit else known
        return {
            "ids": known,
            "metadatas": [self.rows[i][1] for i in known],
            "documents": [self.rows[i][0] for i in known],
        }

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

    def test_파일명도_임베딩_대상에_들어간다(self, fake_collection, monkeypatch, tmp_path):
        # 사람은 기억나는 파일명으로 찾는다. 본문만 임베딩하면 그게 안 된다.
        folder = tmp_path / "3학년1학기"
        folder.mkdir()
        file_a = folder / "운영체제_기말_정리.pdf"
        file_a.write_bytes(b"x")
        monkeypatch.setattr(indexer, "extract_from_path", lambda path, max_chars: [
            extracted(str(file_a), "운영체제_기말_정리.pdf", text="본문에는 제목이 없다")])
        indexer.start(str(tmp_path))
        wait_done()

        stored_text = fake_collection.rows[str(file_a)][0]
        assert "운영체제 기말 정리" in stored_text   # 구분자는 공백으로
        assert "3학년1학기" in stored_text           # 상위 폴더명도 단서다
        assert "본문에는 제목이 없다" in stored_text

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

    def test_한_파일이_임베딩에_실패해도_나머지는_색인된다(
            self, fake_collection, monkeypatch, tmp_path):
        """묶음 하나가 터져도 색인 전체를 포기하면 안 된다.

        예전에는 upsert 예외가 _run 전체를 빠져나가, 임베딩 한 번만 실패해도
        **한 건도 색인되지 않은 채** "완료"가 됐다. 그러면 폴더 안 파일은 다 보이는데
        검색만 죽어 있어 사용자가 원인을 알 수 없다.
        """
        good = tmp_path / "정상문서.pdf"
        bad = tmp_path / "문제문서.pdf"
        good.write_bytes(b"x")
        bad.write_bytes(b"x")
        monkeypatch.setattr(indexer, "extract_from_path", lambda path, max_chars: [
            extracted(str(good), "정상문서.pdf"),
            extracted(str(bad), "문제문서.pdf"),
        ])

        original_upsert = fake_collection.upsert

        def flaky_upsert(ids, documents, metadatas):
            if str(bad) in ids:
                raise RuntimeError("임베딩 서버 응답 없음")
            original_upsert(ids, documents, metadatas)

        monkeypatch.setattr(fake_collection, "upsert", flaky_upsert)

        indexer.start(str(tmp_path))
        state = wait_done()

        assert str(good) in fake_collection.rows      # 멀쩡한 파일은 들어갔다
        assert state["done"] == 1
        assert [f["path"] for f in state["failed"]] == [str(bad)]
        assert "임베딩 서버 응답 없음" in state["failed"][0]["reason"]
        assert not state["error"]                     # 일부 실패는 전체 실패가 아니다

    def test_전부_실패하면_이유를_남긴다(self, fake_collection, monkeypatch, tmp_path):
        # 화면이 "왜 검색이 안 되는지"를 말하려면 백엔드가 이유를 남겨야 한다.
        file_a = tmp_path / "a.pdf"
        file_a.write_bytes(b"x")
        monkeypatch.setattr(indexer, "extract_from_path",
                            lambda path, max_chars: [extracted(str(file_a), "a.pdf")])

        def always_fails(ids, documents, metadatas):
            raise RuntimeError("Ollama 연결 끊김")

        monkeypatch.setattr(fake_collection, "upsert", always_fails)

        indexer.start(str(tmp_path))
        state = wait_done()

        assert state["done"] == 0
        assert "Ollama 연결 끊김" in state["error"]
        assert state["finished_at"]  # 끝났다는 사실 자체는 남아야 화면이 대기를 멈춘다


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


class TestSearchFindsWhatUserRemembers:
    """"다른 PC에 설치했더니 파일명을 그대로 넣어도 못 찾는다"에 대한 회귀 테스트."""

    @pytest.fixture()
    def indexed(self, fake_collection, monkeypatch, tmp_path):
        monkeypatch.setattr(search_module, "check_ollama", lambda *a, **k: (True, ""))
        folder = tmp_path / "학교자료"
        folder.mkdir()

        def add(relative_name: str, text: str):
            path = folder / relative_name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")
            fake_collection.upsert(
                ids=[str(path)],
                documents=[text],
                metadatas=[{"source": "user", "current_name": path.name,
                            "current_path": str(path), "extension": "pdf",
                            "root": str(folder), "mtime_us": 1}])
            return path

        return folder, add

    def test_파일명을_그대로_넣으면_찾는다(self, indexed):
        folder, add = indexed
        target = add("운영체제_기말_정리.pdf", "본문 아무 내용")
        add("네트워크_중간고사.pdf", "전혀 다른 내용")

        response = search_module.search("운영체제_기말_정리.pdf 이거 찾아줘", root=str(folder))
        assert response.hits[0].file.path == str(target)
        assert response.hits[0].score == 1.0

    def test_이름_일부만_기억해도_찾는다(self, indexed):
        folder, add = indexed
        target = add("운영체제_기말_정리.pdf", "본문 아무 내용")

        response = search_module.search("운영체제 기말 자료 있나", root=str(folder))
        assert response.hits[0].file.path == str(target)

    def test_같은_파일이_두_번_나오지_않는다(self, indexed):
        folder, add = indexed
        add("운영체제_기말_정리.pdf", "본문 아무 내용")

        response = search_module.search("운영체제_기말_정리", root=str(folder))
        paths = [hit.file.path for hit in response.hits]
        assert len(paths) == len(set(paths))

    def test_root_표기가_달라도_같은_폴더로_본다(self, indexed):
        folder, add = indexed
        target = add("하위폴더/과제_보고서.pdf", "본문")

        # FE가 보내는 경로 표기는 색인 당시와 다를 수 있다 (끝 슬래시·구분자).
        for notation in (str(folder), str(folder) + "/", str(folder).replace("/", "\\")):
            response = search_module.search("과제_보고서", root=notation)
            assert [hit.file.path for hit in response.hits] == [str(target)], notation

    def test_다른_폴더_파일은_섞이지_않는다(self, indexed, tmp_path):
        folder, add = indexed
        add("과제_보고서.pdf", "본문")

        other = tmp_path / "다른폴더"
        other.mkdir()
        response = search_module.search("과제_보고서", root=str(other))
        assert response.hits == []


class TestIsUnder:
    def test_같은_폴더와_하위_폴더는_통과(self):
        assert search_module._is_under("/home/u/문서/a.pdf", "/home/u/문서")
        assert search_module._is_under("/home/u/문서/하위/a.pdf", "/home/u/문서/")

    def test_이름이_겹치는_옆_폴더는_걸러진다(self):
        # 접두어 비교를 "/" 없이 하면 문서2가 문서의 하위로 잘못 잡힌다.
        assert not search_module._is_under("/home/u/문서2/a.pdf", "/home/u/문서")
