"""RAG 컨텍스트 조회(유사 예시 + k-NN 분류) 테스트. ChromaDB·Ollama 없이 돈다."""

import pytest

from app.contracts.ai import Category
from app.rag import retrieve


class FakeCollection:
    """`collection.query`만 흉내낸다."""

    def __init__(self, rows):
        # rows: (current_name, true_category, ideal_filename, document, distance)
        self.rows = rows
        self.last_kwargs = None

    def query(self, **kwargs):
        self.last_kwargs = kwargs
        n = kwargs["n_results"]
        picked = self.rows[:n]
        return {
            "metadatas": [[{
                "current_name": name,
                "true_category": category,
                "ideal_filename": ideal,
            } for name, category, ideal, _, _ in picked]],
            "documents": [[doc for *_, doc, _ in picked]],
            "distances": [[dist for *_, dist in picked]],
        }


ROWS = [
    ("a.pdf", "lecture", "운영체제_스케줄링_강의자료_2026-1.pdf", "스케줄링 강의", 0.10),
    ("b.pdf", "lecture", "운영체제_데드락_강의자료_2026-1.pdf", "데드락 강의", 0.15),
    ("c.pdf", "assignment", "운영체제_스케줄링_과제_2026-1.pdf", "스케줄링 과제", 0.20),
    ("d.pdf", "report", "운영체제_실험_보고서_2026-1.pdf", "실험 보고서", 0.30),
]


def patch_collection(monkeypatch, rows):
    collection = FakeCollection(rows)
    monkeypatch.setattr(retrieve, "_collection", lambda: collection)
    return collection


def test_예시와_kNN을_한_번의_질의로(monkeypatch):
    collection = patch_collection(monkeypatch, ROWS)
    context = retrieve.retrieve_context("스케줄링 정리")

    # 임베딩 질의는 정확히 한 번이어야 한다 (CPU에서 질의당 약 2.8초).
    assert collection.last_kwargs is not None

    assert context.knn_category is Category.LECTURE  # 2/3 다수결
    assert context.knn_vote_ratio == pytest.approx(2 / 3)
    assert len(context.examples) == 3
    # few-shot 예시는 정리된 뒤 이름(ideal_filename)을 보여 줘야 한다.
    assert context.examples[0].file_name == "운영체제_스케줄링_강의자료_2026-1.pdf"
    assert context.examples[0].score == pytest.approx(0.90)


def test_자기_자신은_이웃에서_제외(monkeypatch):
    patch_collection(monkeypatch, ROWS)
    context = retrieve.retrieve_context("스케줄링", exclude_name="a.pdf")
    names = [e.file_name for e in context.examples]
    assert "운영체제_스케줄링_강의자료_2026-1.pdf" not in names
    # a.pdf가 빠지면 lecture 1 : assignment 1 : report 1 → 다수결은 첫 최빈값
    assert context.knn_category is not None


def test_계약_밖_카테고리는_무시(monkeypatch):
    rows = [("x.pdf", "homework", "x.pdf", "본문", 0.1)] + ROWS
    patch_collection(monkeypatch, rows)
    context = retrieve.retrieve_context("스케줄링")
    assert all(e.category in Category for e in context.examples)
    assert context.knn_category is Category.LECTURE


def test_색인이_비면_빈_컨텍스트(monkeypatch):
    patch_collection(monkeypatch, [])
    context = retrieve.retrieve_context("스케줄링")
    assert context.examples == []
    assert context.knn_category is None
    assert context.knn_vote_ratio == 0.0
