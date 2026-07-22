"""
개발용 가짜 QA 데이터셋을 만드는 스크립트입니다.

1주차에 FE/BE가 실제 모델 없이도 데이터 흐름을 맞춰볼 수 있도록,
템플릿 기반의 질문/답변 JSONL 파일을 생성합니다.
"""

import json
import random
from pathlib import Path


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


def generate_count(n: int, source_dir: Path = None):
    """지정한 개수만큼 가짜 QA 데이터를 생성합니다."""
    out = []
    samples = []
    if source_dir and source_dir.exists():
        for f in source_dir.iterdir():
            if f.suffix.lower() in {".pdf", ".txt", ".md"}:
                try:
                    # 개발용 데이터 생성이라 TXT/MD는 단순 텍스트 읽기로 충분합니다.
                    text = f.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    text = ""
                samples.append(text)

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
