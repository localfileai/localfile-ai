"""POST /organize 라우트 테스트. 추출·RAG·LLM을 전부 가짜로 주입해 Ollama 없이 돈다."""

import json

import pytest
from fastapi.testclient import TestClient

from app import create_app
from app.api.routes import organize as organize_route
from app.contracts.ai import Category, OrganizeResponse
from app.rag.retrieve import RagContext
from app.contracts.ai import RetrievedExample

VALID_FULL = json.dumps({
    "category": "assignment",
    "recommended_folder": "assignment/데이터베이스/2025-1",
    "recommended_filename": "데이터베이스_정규화_과제_2025-1.pdf",
    "confidence": 0.9,
    "reason": "문서 유형이 과제로 명시되어 있다.",
}, ensure_ascii=False)


@pytest.fixture()
def client():
    return TestClient(create_app())


def extracted_item(path="C:/Users/a/Downloads/최종.pdf", name="최종.pdf",
                   extension=".pdf", text="정규화 과제", error=""):
    return {
        "path": path, "name": name, "extension": extension,
        "raw_text": text, "normalized_text": text, "preview_text": text,
        "error": error,
    }


@pytest.fixture()
def happy_path(monkeypatch):
    """LLM 준비 완료 + 파일 1건 추출 + RAG 컨텍스트가 있는 기본 상황."""
    monkeypatch.setattr(organize_route.llm_client, "check_generate_model",
                        lambda model: (True, ""))
    monkeypatch.setattr(organize_route, "extract_from_path",
                        lambda path, max_chars: [extracted_item()])
    monkeypatch.setattr(organize_route, "retrieve_context",
                        lambda text, **kw: RagContext(
                            examples=[RetrievedExample(
                                file_name="데이터베이스_SQL_과제_2025-1.pdf",
                                category=Category.ASSIGNMENT,
                                first_page_text="...", score=0.8)],
                            knn_category=Category.ASSIGNMENT,
                            knn_vote_ratio=1.0))
    monkeypatch.setattr(organize_route.llm_client, "generate",
                        lambda system, prompt, model=None, **kw: VALID_FULL)
    return monkeypatch


def test_LLM이_준비되지_않으면_503(client, monkeypatch):
    monkeypatch.setattr(organize_route.llm_client, "check_generate_model",
                        lambda model: (False, "생성 모델이 없습니다: exaone3.5:7.8b"))
    response = client.post("/organize", json={"path": "C:/Users/a/Documents"})
    assert response.status_code == 503
    assert "exaone" in response.json()["detail"]


def test_잘못된_경로는_400(client, monkeypatch):
    monkeypatch.setattr(organize_route.llm_client, "check_generate_model",
                        lambda model: (True, ""))

    def boom(path, max_chars):
        raise FileNotFoundError(path)

    monkeypatch.setattr(organize_route, "extract_from_path", boom)
    response = client.post("/organize", json={"path": "C:/없는/폴더"})
    assert response.status_code == 400


def test_모르는_mode는_422(client):
    response = client.post("/organize", json={"path": "a", "mode": "turbo"})
    assert response.status_code == 422


def test_full_모드_정상_추천(client, happy_path):
    response = client.post("/organize", json={"path": "C:/Users/a/Downloads"})
    assert response.status_code == 200

    body = OrganizeResponse.model_validate(response.json())  # 팀 계약으로 응답 검증
    assert body.total_files == 1
    assert body.success_count == 1
    assert body.failed == []
    suggestion = body.suggestions[0].suggestion
    assert suggestion.category is Category.ASSIGNMENT
    assert suggestion.recommended_filename.endswith(".pdf")


def test_추출_실패_파일은_failed로_분리(client, happy_path, monkeypatch):
    monkeypatch.setattr(organize_route, "extract_from_path", lambda path, max_chars: [
        extracted_item(),
        extracted_item(path="C:/a/스캔.pdf", name="스캔.pdf", text="", error="텍스트 레이어 없음"),
    ])
    response = client.post("/organize", json={"path": "C:/a"})
    body = OrganizeResponse.model_validate(response.json())
    assert body.total_files == 2
    assert body.success_count == 1
    assert len(body.failed) == 1
    assert "텍스트 레이어 없음" in body.failed[0].reason


def test_slim_모드는_kNN_분류를_쓴다(client, happy_path, monkeypatch):
    monkeypatch.setattr(
        organize_route.llm_client, "generate",
        lambda system, prompt, model=None, **kw:
            json.dumps({"recommended_filename": "데이터베이스_정규화_과제_2025-1"},
                       ensure_ascii=False))
    response = client.post("/organize", json={"path": "C:/a", "mode": "slim"})
    body = OrganizeResponse.model_validate(response.json())
    assert body.success_count == 1
    suggestion = body.suggestions[0].suggestion
    assert suggestion.category is Category.ASSIGNMENT   # k-NN 결과
    assert suggestion.recommended_filename.endswith(".pdf")  # 확장자 보정
    assert "k-NN" in suggestion.reason


def test_slim_모드에서_색인이_없으면_파일은_실패_처리(client, happy_path, monkeypatch):
    monkeypatch.setattr(organize_route, "retrieve_context",
                        lambda text, **kw: RagContext())
    response = client.post("/organize", json={"path": "C:/a", "mode": "slim"})
    body = OrganizeResponse.model_validate(response.json())
    assert body.success_count == 0
    assert "knn_unavailable" in body.failed[0].reason


def test_use_rag_false면_예시_없이_프롬프트(client, happy_path, monkeypatch):
    prompts = []

    def spy_generate(system, prompt, model=None, **kw):
        prompts.append(prompt)
        return VALID_FULL

    monkeypatch.setattr(organize_route.llm_client, "generate", spy_generate)
    client.post("/organize", json={"path": "C:/a", "use_rag": False})
    assert "비슷한 문서들은" not in prompts[0]

    prompts.clear()
    client.post("/organize", json={"path": "C:/a", "use_rag": True})
    assert "비슷한 문서들은" in prompts[0]
