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


@pytest.fixture(autouse=True)
def reset_auto_cache():
    """auto 모드 판정 캐시가 테스트 간에 새지 않게 한다."""
    organize_route._auto_resolved.update({"mode": None, "probe_sec": None})
    yield
    organize_route._auto_resolved.update({"mode": None, "probe_sec": None})


@pytest.fixture()
def happy_path(monkeypatch):
    """LLM 준비 완료 + 파일 1건 추출 + 임베딩·분류·RAG가 있는 기본 상황.

    속도 프로브는 빠른 기기(0.5s)로 고정 → 기본값 auto가 full로 판정된다.
    """
    from app.rag.classify import ClassifyResult

    monkeypatch.setattr(organize_route.llm_client, "check_generate_model",
                        lambda model: (True, ""))
    monkeypatch.setattr(organize_route.llm_client, "probe_generation_seconds",
                        lambda model: 0.5)
    monkeypatch.setattr(organize_route, "extract_from_path",
                        lambda path, max_chars: [extracted_item()])
    monkeypatch.setattr(organize_route.classify, "embed_text",
                        lambda text: [0.1] * 8)
    monkeypatch.setattr(organize_route.classify, "classify_vector",
                        lambda vector, feedback=None: ClassifyResult(
                            Category.ASSIGNMENT, 0.82, "label_zeroshot"))
    monkeypatch.setattr(organize_route, "feedback_collection",
                        lambda create=False: None)
    monkeypatch.setattr(organize_route, "retrieve_context",
                        lambda *a, **kw: RagContext(
                            examples=[RetrievedExample(
                                file_name="데이터베이스_SQL_과제_2025-1.pdf",
                                category=Category.ASSIGNMENT,
                                first_page_text="...", score=0.8)]))
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


def test_offset으로_다음_묶음을_이어서_분석(client, happy_path, monkeypatch):
    """상한(max_files)을 넘는 폴더의 "이어서 분석" 회귀 테스트.

    80개 폴더에서 20개를 분석한 뒤, offset=20으로 다시 부르면 그다음 묶음이
    처리되어야 한다. total_files는 offset과 무관하게 전체 발견 수다.
    """
    files = [extracted_item(path=f"C:/a/문서{i:02d}.pdf", name=f"문서{i:02d}.pdf")
             for i in range(5)]
    monkeypatch.setattr(organize_route, "extract_from_path",
                        lambda path, max_chars: files)

    first = client.post("/organize", json={"path": "C:/a", "max_files": 2}).json()
    second = client.post("/organize", json={"path": "C:/a", "max_files": 2,
                                            "offset": 2}).json()

    assert first["total_files"] == 5 and second["total_files"] == 5
    names = lambda body: [s["current"]["name"] for s in body["suggestions"]]  # noqa: E731
    assert names(first) == ["문서00.pdf", "문서01.pdf"]
    assert names(second) == ["문서02.pdf", "문서03.pdf"]


def test_slim_모드는_자동_분류를_쓴다(client, happy_path, monkeypatch):
    options = []

    def generate(system, prompt, model=None, **kw):
        options.append(kw)
        return json.dumps({"recommended_filename": "데이터베이스_정규화_과제_2025-1"},
                          ensure_ascii=False)

    monkeypatch.setattr(
        organize_route.llm_client, "generate", generate)
    response = client.post("/organize", json={"path": "C:/a", "mode": "slim"})
    body = OrganizeResponse.model_validate(response.json())
    assert body.success_count == 1
    suggestion = body.suggestions[0].suggestion
    assert suggestion.category is Category.ASSIGNMENT   # 자동 분류 결과
    assert suggestion.recommended_filename.endswith(".pdf")  # 확장자 보정
    assert "분류" in suggestion.reason
    assert options[0]["num_predict"] == organize_route.config.SLIM_NUM_PREDICT


def test_slim_모드에서_임베딩이_안_되면_파일은_실패_처리(client, happy_path, monkeypatch):
    def broken(text):
        raise RuntimeError("Ollama 연결 실패")

    monkeypatch.setattr(organize_route.classify, "embed_text", broken)
    response = client.post("/organize", json={"path": "C:/a", "mode": "slim"})
    body = OrganizeResponse.model_validate(response.json())
    assert body.success_count == 0
    assert "classify_unavailable" in body.failed[0].reason


def test_auto_모드는_느린_기기에서_slim으로_강등(client, happy_path, monkeypatch):
    monkeypatch.setattr(organize_route.llm_client, "probe_generation_seconds",
                        lambda model: 12.0)  # CPU 수준으로 느림
    monkeypatch.setattr(
        organize_route.llm_client, "generate",
        lambda system, prompt, model=None, **kw:
            json.dumps({"recommended_filename": "데이터베이스_정규화_과제_2025-1.pdf"},
                       ensure_ascii=False))
    response = client.post("/organize", json={"path": "C:/a", "mode": "auto"})
    body = OrganizeResponse.model_validate(response.json())
    assert "분류" in body.suggestions[0].suggestion.reason  # slim 경로로 실행됨


def test_auto_모드_빠른_기기는_full_유지(client, happy_path):
    response = client.post("/organize", json={"path": "C:/a", "mode": "auto"})
    body = OrganizeResponse.model_validate(response.json())
    assert "k-NN" not in body.suggestions[0].suggestion.reason  # full 경로


def test_auto_판정은_한_번만_재고_캐시된다(client, happy_path, monkeypatch):
    calls = []

    def probe(model):
        calls.append(model)
        return 0.5

    monkeypatch.setattr(organize_route.llm_client, "probe_generation_seconds", probe)
    client.post("/organize", json={"path": "C:/a", "mode": "auto"})
    client.post("/organize", json={"path": "C:/a", "mode": "auto"})
    assert len(calls) == 1


def test_프로브_실패면_안전하게_slim(client, happy_path, monkeypatch):
    from app.llm.client import LLMRequestError

    def broken_probe(model):
        raise LLMRequestError("timeout")

    monkeypatch.setattr(organize_route.llm_client, "probe_generation_seconds", broken_probe)
    monkeypatch.setattr(
        organize_route.llm_client, "generate",
        lambda system, prompt, model=None, **kw:
            json.dumps({"recommended_filename": "a_b_2025-1.pdf"}))
    response = client.post("/organize", json={"path": "C:/a", "mode": "auto"})
    body = OrganizeResponse.model_validate(response.json())
    assert "분류" in body.suggestions[0].suggestion.reason


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
