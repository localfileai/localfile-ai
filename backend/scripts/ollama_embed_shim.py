"""Ollama 호환 임베딩 심(shim) 서버 — Ollama를 설치할 수 없는 환경용.

클라우드 세션·CI처럼 Ollama(및 bge-m3)를 받을 수 없는 곳에서 검색 스택
(`embed_dataset.py` → ChromaDB → `/search` → `eval_search.py`)을 **코드 수정 없이**
실제로 돌리기 위해 Ollama의 임베딩 API 두 개를 흉내낸다.

    GET  /api/tags    → 설치된 모델 목록 (check_ollama 통과용)
    POST /api/embed   → {"model", "input": [...]} → {"embeddings": [[...], ...]}

뒤에는 `intfloat/multilingual-e5-large`(ONNX, 1024차원)를 물린다. bge-m3와
같은 차원의 다국어 검색 모델이라 대체 측정에 적합하다. e5 계열은 비대칭
접두사를 쓰므로 **모델 이름으로 접두사를 고른다**:

    e5-passage  → "passage: " + 텍스트   (색인할 문서)
    e5-query    → "query: "   + 텍스트   (검색 질의)

준비 (모델 파일은 GCS에서 공개 배포된다):
    curl -L -o e5.tar.gz https://storage.googleapis.com/qdrant-fastembed/fast-multilingual-e5-large.tar.gz
    tar -xzf e5.tar.gz -C .fastembed_cache
    pip install onnxruntime tokenizers numpy

실행:
    python scripts/ollama_embed_shim.py            # 127.0.0.1:11434
    python scripts/ollama_embed_shim.py --port 11435

⚠️ 이 심으로 만든 색인과 bge-m3 색인은 호환되지 않는다. 실기기(bge-m3) 수치와
   비교할 때는 반드시 "대체 모델(e5) 측정"임을 함께 적을 것.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parents[1] / ".fastembed_cache" / "fast-multilingual-e5-large"

PREFIXES = {
    "e5-passage": "passage: ",
    "e5-query": "query: ",
}


class Embedder:
    """multilingual-e5-large ONNX + 평균 풀링 + L2 정규화."""

    def __init__(self, model_dir: Path) -> None:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.np = np
        self.tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=512)
        self.session = ort.InferenceSession(
            str(model_dir / "model.onnx"), providers=["CPUExecutionProvider"])

    def embed(self, texts: list[str], prefix: str) -> list[list[float]]:
        np = self.np
        encodings = self.tokenizer.encode_batch([prefix + t for t in texts])
        maxlen = max(len(e.ids) for e in encodings)
        # XLM-RoBERTa 계열의 pad 토큰 id는 1이다.
        ids = np.array([e.ids + [1] * (maxlen - len(e.ids)) for e in encodings], dtype=np.int64)
        mask = np.array([e.attention_mask + [0] * (maxlen - len(e.attention_mask))
                         for e in encodings], dtype=np.int64)
        hidden = self.session.run(None, {"input_ids": ids, "attention_mask": mask})[0]
        weights = mask[..., None].astype(np.float32)
        vectors = (hidden * weights).sum(1) / weights.sum(1)
        vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors.tolist()


def make_handler(embedder: Embedder):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/api/tags":
                self._json({"models": [{"name": f"{name}:latest"} for name in PREFIXES]})
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            if self.path != "/api/embed":
                self._json({"error": "not found"}, 404)
                return
            length = int(self.headers.get("Content-Length", 0))
            request = json.loads(self.rfile.read(length))
            model = str(request.get("model", "")).split(":")[0]
            prefix = PREFIXES.get(model)
            if prefix is None:
                self._json({"error": f"model {model!r} not found"}, 404)
                return
            texts = request.get("input", [])
            if isinstance(texts, str):
                texts = [texts]
            started = time.perf_counter()
            embeddings = embedder.embed([str(t) for t in texts], prefix)
            print(f"  embed {model:<10} {len(texts):>3}건 {time.perf_counter() - started:6.2f}s",
                  flush=True)
            self._json({"model": model, "embeddings": embeddings})

        def log_message(self, *args):  # 기본 액세스 로그는 소음이라 끈다.
            pass

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Ollama 호환 임베딩 심 서버")
    parser.add_argument("--port", type=int, default=11434)
    parser.add_argument("--model-dir", type=Path, default=MODEL_DIR)
    args = parser.parse_args()

    if not (args.model_dir / "model.onnx").exists():
        print(f"[에러] 모델 없음: {args.model_dir}\n"
              "  위 docstring의 curl 명령으로 먼저 내려받으세요.", file=sys.stderr)
        return 1

    print(f"[로딩] {args.model_dir.name} ...", flush=True)
    embedder = Embedder(args.model_dir)
    print(f"[시작] http://127.0.0.1:{args.port}  모델: {', '.join(PREFIXES)}", flush=True)
    HTTPServer(("127.0.0.1", args.port), make_handler(embedder)).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
