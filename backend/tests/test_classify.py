"""분류 3방식 통합(classify.py)·피드백 API 테스트. ChromaDB·Ollama 없이 돈다."""

import pytest
from fastapi.testclient import TestClient

from app import create_app
from app.api.routes import feedback as feedback_route
from app.contracts.ai import Category
from app.core import config
from app.rag import classify


def make_label_vectors(monkeypatch):
    """라벨 정의문 좌표를 직교 기저 벡터로 주입한다 (임베딩 호출 차단)."""
    import numpy as np

    labels = list(classify.LABEL_DEFINITIONS)
    matrix = np.eye(len(labels), dtype=np.float32)
    monkeypatch.setattr(classify, "_label_vectors", lambda: (labels, matrix))
    return labels


class FakeFeedbackCollection:
    def __init__(self, rows=None):
        self.rows = rows or []  # [(category_str, distance)]

    def count(self):
        return len(self.rows)

    def query(self, query_embeddings, n_results):
        picked = self.rows[:n_results]
        return {
            "metadatas": [[{"category": category} for category, _ in picked]],
            "distances": [[distance for _, distance in picked]],
        }

    def upsert(self, ids, embeddings, documents, metadatas):
        for metadata in metadatas:
            self.rows.append((metadata["category"], 0.1))


class TestClassifyVector:
    def test_가장_가까운_라벨_정의문으로_분류(self, monkeypatch):
        labels = make_label_vectors(monkeypatch)
        target = labels.index(Category.ASSIGNMENT)
        vector = [0.0] * len(labels)
        vector[target] = 1.0

        result = classify.classify_vector(vector)
        assert result.category is Category.ASSIGNMENT
        assert result.method == "label_zeroshot"
        assert result.confidence >= config.CLASSIFY_MIN_SIMILARITY

    def test_어디에도_가깝지_않으면_etc_보류(self, monkeypatch):
        labels = make_label_vectors(monkeypatch)
        # 모든 라벨에 균등하게 걸친 벡터 — 정규화 후 어느 정의문과도 1/√9≈0.33 < 임계값
        vector = [1.0] * len(labels)

        result = classify.classify_vector(vector)
        assert result.category is Category.ETC
        assert result.method == "etc_fallback"

    def test_사용자_예시가_라벨_정의문보다_우선(self, monkeypatch):
        labels = make_label_vectors(monkeypatch)
        target = labels.index(Category.LECTURE)
        vector = [0.0] * len(labels)
        vector[target] = 1.0  # 정의문 기준으로는 lecture

        # 그러나 사용자가 비슷한 문서를 personal로 승인해 왔다면 그쪽을 따른다.
        feedback = FakeFeedbackCollection(rows=[("personal", 0.2), ("personal", 0.3)])
        result = classify.classify_vector(vector, feedback)
        assert result.category is Category.PERSONAL
        assert result.method == "user_knn"

    def test_사용자_예시가_멀면_무시하고_정의문으로(self, monkeypatch):
        labels = make_label_vectors(monkeypatch)
        target = labels.index(Category.REPORT)
        vector = [0.0] * len(labels)
        vector[target] = 1.0

        # 유사도 = 1-거리 < CLASSIFY_USER_MIN_SIMILARITY → 참조 안 함
        feedback = FakeFeedbackCollection(rows=[("personal", 0.9)])
        result = classify.classify_vector(vector, feedback)
        assert result.category is Category.REPORT
        assert result.method == "label_zeroshot"

    def test_라벨_정의문은_전_카테고리를_다룬다(self):
        # ETC는 비교 대상이 아니라 결과이므로 정의문에서 빠져야 한다.
        assert set(classify.LABEL_DEFINITIONS) == set(Category) - {Category.ETC}


class TestFeedbackApi:
    @pytest.fixture()
    def client(self):
        return TestClient(create_app())

    @pytest.fixture()
    def stores(self, monkeypatch):
        collection = FakeFeedbackCollection()
        monkeypatch.setattr(feedback_route, "feedback_collection",
                            lambda create=False: collection)
        monkeypatch.setattr(feedback_route.classify, "embed_text", lambda text: [0.1] * 8)
        return collection

    def test_피드백_저장(self, client, stores):
        response = client.post("/feedback", json={
            "path": "C:/Users/a/Documents/최종.pdf",
            "category": "assignment",
            "filename": "데이터베이스_정규화_과제_2025-1.pdf",
            "first_page_text": "정규화 과제 본문...",
        })
        assert response.status_code == 201
        assert response.json()["examples"] == 1
        assert stores.rows[0][0] == "assignment"

    def test_모르는_카테고리는_422(self, client, stores):
        response = client.post("/feedback", json={
            "path": "C:/a.pdf", "category": "homework", "first_page_text": "..."})
        assert response.status_code == 422

    def test_텍스트_없으면_파일에서_추출(self, client, stores, monkeypatch, tmp_path):
        target = tmp_path / "문서.pdf"
        target.write_bytes(b"x")
        monkeypatch.setattr(
            feedback_route, "extract_from_path",
            lambda path, max_chars: [{"path": str(target), "name": "문서.pdf",
                                      "extension": ".pdf", "raw_text": "추출된 본문",
                                      "normalized_text": "추출된 본문",
                                      "preview_text": "추출된 본문", "error": ""}])
        response = client.post("/feedback", json={
            "path": str(target), "category": "etc"})
        assert response.status_code == 201

    def test_상태_조회(self, client, stores):
        stores.rows.append(("lecture", 0.1))
        assert client.get("/feedback/status").json()["examples"] == 1
