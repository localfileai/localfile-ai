"""
개발용 가짜 QA 데이터셋을 만드는 스크립트입니다.

1주차에 FE/BE가 실제 모델 없이도 데이터 흐름을 맞춰볼 수 있도록,
템플릿 기반의 질문/답변 JSONL 파일을 생성합니다.
"""

import json
import random
import sys
from pathlib import Path
from typing import List, Optional

# 스크립트를 `python scripts/...` 형태로 실행해도 app 패키지를 import할 수 있게 합니다.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.fileops import extract_from_path


TEMPLATES = [
    # 질문 템플릿과 답변 템플릿을 짝으로 보관합니다.
    ("문서의 주제는 무엇인가요?", "{title} 문서는 주로 {topic}에 대해 설명합니다."),
    ("요약을 한 문장으로 알려줘.", "{title}의 요약: {summary}"),
    ("추천 파일명은?", "{title}_요약.txt"),
]


def make_pair(source_text: str, idx: int) -> dict:
    """원본 텍스트 하나를 기반으로 가짜 질문/답변 한 쌍을 만듭니다."""
    title = f"문서{idx}"
    topic = random.choice(["계약", "보고서", "설명서", "회의록", "정책"])
    summary = (source_text.strip().split('\n')[0][:120] + '...') if source_text else "요약 없음"
    q, a = random.choice(TEMPLATES)
    answer = a.format(title=title, topic=topic, summary=summary)
    return {"id": idx, "question": q, "context": source_text[:2000], "answer": answer}


def load_source_texts(source_dir: Optional[Path]) -> List[str]:
    """PDF/TXT/MD 문서에서 전처리된 텍스트만 모아 데이터셋 재료로 사용합니다."""
    samples = []
    if not source_dir or not source_dir.exists():
        return samples

    # 1주차 핵심 전처리 로직을 재사용합니다.
    # PDF는 첫 페이지만, TXT/MD는 텍스트를 읽어 AI가 과하게 긴 문서를 받지 않도록 합니다.
    for item in extract_from_path(str(source_dir), max_chars=2000):
        # RAG 데이터셋은 검색/임베딩 품질이 중요하므로 정규화된 텍스트를 사용합니다.
        if item["normalized_text"] and not item["error"]:
            samples.append(item["normalized_text"])
    return samples


def generate_count(n: int, source_dir: Optional[Path] = None):
    """지정한 개수만큼 가짜 QA 데이터를 생성합니다."""
    out = []
    samples = load_source_texts(source_dir)

    for i in range(1, n + 1):
        src = random.choice(samples) if samples else f"예시 텍스트 {i}"
        out.append(make_pair(src, i))

    return out


def main():
    """명령행 옵션을 받아 JSONL 파일을 생성합니다."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("-n", type=int, default=1000)
    parser.add_argument("--source-dir", type=str, default=None)
    parser.add_argument("--out", type=str, default="fake_dataset.jsonl")
    args = parser.parse_args()

    src = Path(args.source_dir) if args.source_dir else None
    pairs = generate_count(args.n, src)
    outp = Path(args.out)

    # 한 줄에 JSON 하나씩 저장하면 나중에 임베딩 스크립트에서 순차 처리하기 쉽습니다.
    with outp.open("w", encoding="utf-8") as fh:
        for p in pairs:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")

    print(f"Wrote {len(pairs)} pairs to {outp}")


if __name__ == "__main__":
    main()
