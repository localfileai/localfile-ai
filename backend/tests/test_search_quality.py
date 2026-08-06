"""검색 품질 회귀 테스트 — "공모전 자료" 시나리오 (5주차 실사용 보고).

실사용에서 두 가지가 무너졌다.
  - "최근 공모전 자료 찾아줘": 공모전 파일 하나 + 무관한 파일들이 나왔다.
  - "공모전 자료": 관련 파일이 아예 안 나왔다 (이름에 "공모전"이 없는 문서는
    파일명 대조에 안 걸리고, 벡터 순위만으로는 변별이 안 됐다).

ChromaDB·Ollama 없이 대역으로 돈다 — 벡터 유사도는 시나리오가 정한 값이다.
"""

from datetime import datetime, timedelta

import pytest

from app.rag import embedding, search as search_module


class FakeCollection:
    """벡터 유사도를 시나리오가 직접 정하는 검색 대역."""

    def __init__(self):
        self.entries: list[dict] = []

    def add(self, name: str, text: str = "", sim: float = 0.0,
            mtime: datetime | None = None):
        path = f"C:/자료/{name}"
        self.entries.append({
            "id": path, "name": name, "text": text, "sim": sim,
            "mtime_us": int(mtime.timestamp() * 1_000_000) if mtime else 0,
        })

    def _meta(self, entry: dict) -> dict:
        return {"source": "user", "current_name": entry["name"],
                "current_path": entry["id"], "extension": "pdf",
                "mtime_us": entry["mtime_us"]}

    def count(self):
        return len(self.entries)

    def get(self, ids=None, include=None, limit=None):
        picked = self.entries[:limit] if limit else self.entries
        return {
            "ids": [e["id"] for e in picked],
            "metadatas": [self._meta(e) for e in picked],
            "documents": [e["text"] for e in picked],
        }

    def query(self, query_texts=None, query_embeddings=None, n_results=10):
        ordered = sorted(self.entries, key=lambda e: e["sim"], reverse=True)
        ordered = ordered[:n_results]
        return {
            "ids": [[e["id"] for e in ordered]],
            "metadatas": [[self._meta(e) for e in ordered]],
            "documents": [[e["text"] for e in ordered]],
            "distances": [[1.0 - e["sim"] for e in ordered]],
        }


@pytest.fixture()
def searchable(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(search_module, "check_ollama", lambda *a, **k: (True, ""))
    monkeypatch.setattr(search_module, "_active_collection",
                        lambda: (collection, "user"))
    monkeypatch.setattr(search_module, "embed_query",
                        lambda text, model=None: [0.0] * 8)
    return collection


def names(response) -> list[str]:
    return [hit.file.name for hit in response.hits]


class Test공모전_시나리오:
    def test_본문에만_공모전이_있어도_찾는다(self, searchable):
        # "공모전 자료"로 검색하면 이름에 공모전이 없는 계획서도 나와야 한다.
        searchable.add("교내공모전_안내.pdf", "참가 부문과 일정 안내", sim=0.55)
        searchable.add("아이디어_경진대회_계획서.pdf", "교내 공모전 출품 계획", sim=0.50)
        searchable.add("노래가사모음.pdf", "좋아하는 노래 가사", sim=0.52)

        response = search_module.search("공모전 자료")

        # 관련 문서 2건이 나란히 위, 무관한 파일이 그 사이를 비집지 못한다.
        assert names(response)[:2] == [
            "교내공모전_안내.pdf", "아이디어_경진대회_계획서.pdf"]

    def test_관련없는_파일로_top_k를_채우지_않는다(self, searchable):
        searchable.add("교내공모전_안내.pdf", "참가 부문과 일정 안내", sim=0.55)
        # 키워드가 전혀 안 맞고 유사도도 어중간한 파일들 — 예전에는 이런 것이
        # top_k를 채웠다.
        searchable.add("노래가사모음.pdf", "좋아하는 노래 가사", sim=0.40)
        searchable.add("수업필기.pdf", "미적분 필기", sim=0.30)

        response = search_module.search("공모전 자료", top_k=5)

        assert names(response) == ["교내공모전_안내.pdf"]

    def test_최근_의도는_최신_파일을_위로(self, searchable):
        now = datetime.now()
        searchable.add("공모전_기획_2023.pdf", "공모전 기획", sim=0.55,
                       mtime=now - timedelta(days=700))
        searchable.add("공모전_기획_최종.pdf", "공모전 기획", sim=0.55,
                       mtime=now - timedelta(days=2))

        response = search_module.search("최근 공모전 자료 찾아줘")

        assert names(response)[0] == "공모전_기획_최종.pdf"

    def test_최근_의도가_없으면_관련도가_우선(self, searchable):
        now = datetime.now()
        # 옛 파일이 뚜렷이 더 관련 있으면 최신 파일이 그걸 밀어내면 안 된다.
        searchable.add("공모전_수상작_분석.pdf", "공모전 수상작 분석", sim=0.70,
                       mtime=now - timedelta(days=700))
        searchable.add("공모전_메모.pdf", "잡담", sim=0.45,
                       mtime=now - timedelta(days=1))

        response = search_module.search("공모전 수상작 분석")

        assert names(response)[0] == "공모전_수상작_분석.pdf"

    def test_파일명_통째_붙여넣기는_만점(self, searchable):
        # 벡터 유사도가 낮게 나와도 (짧은 질의 + 조사) 이름 그대로면 반드시 1위.
        searchable.add("운영체제_기말_정리.pdf", "본문", sim=0.2)

        response = search_module.search("운영체제_기말_정리.pdf 이거 찾아줘")

        assert names(response) == ["운영체제_기말_정리.pdf"]
        assert response.hits[0].score == 1.0

    def test_발췌는_키워드가_나온_대목을_보여준다(self, searchable):
        filler = "서론 문단입니다. " * 60          # 키워드가 500자 상한 밖에 있게
        searchable.add("안내문.pdf", filler + "여기서 공모전 접수 방법을 설명한다",
                       sim=0.6)

        response = search_module.search("공모전")

        assert "공모전" in response.hits[0].matched_text

    def test_임베딩이_죽어도_키워드_검색은_동작(self, searchable, monkeypatch):
        def broken(text, model=None):
            raise embedding.EmbeddingUnavailable("모델 준비 중")
        monkeypatch.setattr(search_module, "embed_query", broken)
        searchable.add("교내공모전_안내.pdf", "참가 안내", sim=0.55)

        response = search_module.search("공모전")

        assert names(response) == ["교내공모전_안내.pdf"]


class TestParseQuery:
    def test_군말과_일반명사는_키워드에서_뺀다(self):
        tokens, temporal, _ = search_module.parse_query("공모전 자료 찾아줘")
        assert tokens == ["공모전"]
        assert temporal is False

    def test_조사가_붙어도_어간을_잡는다(self):
        tokens, _, _ = search_module.parse_query("공모전에서 받은 것")
        assert "공모전" in tokens

    def test_두_글자_단어의_끝소리는_조사가_아니다(self):
        # "회의"의 "의"를 조사로 떼면 안 된다.
        tokens, _, _ = search_module.parse_query("회의 기록")
        assert "회의" in tokens

    def test_시간표현은_키워드가_아니라_최신성_신호(self):
        tokens, temporal, cleaned = search_module.parse_query("최근 공모전 자료")
        assert temporal is True
        assert tokens == ["공모전"]
        assert "최근" not in cleaned


class TestEmbedQuery:
    def test_qwen3는_질의에_검색_지시문을_붙인다(self, monkeypatch):
        captured = {}

        def fake_embed(model, inputs, timeout):
            captured["model"], captured["input"] = model, inputs[0]
            return [[0.1, 0.2]]
        monkeypatch.setattr(embedding, "_embed", fake_embed)

        embedding.embed_query("공모전 자료", model="qwen3-embedding:0.6b")
        assert captured["input"].startswith("Instruct:")
        assert captured["input"].endswith("공모전 자료")

    def test_다른_모델은_지시문_없이_그대로(self, monkeypatch):
        captured = {}

        def fake_embed(model, inputs, timeout):
            captured["input"] = inputs[0]
            return [[0.1, 0.2]]
        monkeypatch.setattr(embedding, "_embed", fake_embed)

        embedding.embed_query("공모전 자료", model="nomic-embed-text")
        assert captured["input"] == "공모전 자료"
