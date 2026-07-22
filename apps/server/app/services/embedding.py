"""
텍스트 임베딩을 담당하는 서비스 파일입니다.

현재는 sentence-transformers를 사용하지만,
나중에 Ollama나 다른 로컬 임베딩 모델로 교체할 수 있도록 클래스로 감싸두었습니다.
"""
from typing import List


class EmbeddingService:
    """문장 리스트를 벡터로 변환하는 얇은 래퍼 클래스입니다."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            # 모델 로딩 비용이 있으므로 객체 생성 시점에만 import합니다.
            from sentence_transformers import SentenceTransformer
        except Exception:
            raise RuntimeError("sentence-transformers is required. pip install sentence-transformers")

        self.model = SentenceTransformer(model_name)

    def embed_texts(self, texts: List[str]):
        """여러 텍스트를 한 번에 임베딩 벡터로 변환합니다."""
        return self.model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
