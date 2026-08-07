"""4단계: file_metadata.csv 일부를 ChromaDB에 임베딩하고 한국어 검색 품질을 점검한다."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import chromadb

COLLECTION_NAME = "file_examples"
SUCCESS_STATUS = "success"

# 3단계 검증 쿼리. 각 쿼리에 대해 "이 카테고리면 납득 가능"한 후보를 함께 적어 둔다.
VERIFICATION_QUERIES: list[tuple[str, set[str]]] = [
    ("데이터베이스 정규화 과제", {"assignment", "practice", "lecture"}),
    ("머신러닝 실험 결과", {"research", "project", "practice"}),
    ("팀 프로젝트 회의록", {"team_project", "project"}),
]


def load_success_rows(csv_path: Path, limit: int) -> list[dict[str, str]]:
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if r["extraction_status"] == SUCCESS_STATUS]
    return rows[:limit]


def build_collection(client: chromadb.ClientAPI, rows: list[dict[str, str]]):
    # 재실행을 멱등하게 만들기 위해 기존 컬렉션을 지우고 새로 만든다.
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"[정리] 기존 컬렉션 {COLLECTION_NAME!r} 삭제")
    except Exception:
        pass

    collection = client.create_collection(name=COLLECTION_NAME)
    collection.add(
        ids=[row["index"] for row in rows],
        documents=[row["first_page_text"] for row in rows],
        metadatas=[
            {
                "category": row["category"],
                "relative_path": row["relative_path"],
                "file_name": row["file_name"],
            }
            for row in rows
        ],
    )
    return collection


def run_queries(collection, n_results: int) -> int:
    """검증 쿼리를 실행하고, 최상위 결과가 주제에 맞은 건수를 돌려준다."""
    hits = 0
    for query, acceptable in VERIFICATION_QUERIES:
        print("\n" + "=" * 72)
        print(f"[쿼리] {query}")
        print(f"  납득 가능한 category: {sorted(acceptable)}")
        print("=" * 72)

        result = collection.query(query_texts=[query], n_results=n_results)
        metadatas = result["metadatas"][0]
        documents = result["documents"][0]
        distances = result["distances"][0]

        if not metadatas:
            print("  (결과 없음)")
            continue

        for rank, (meta, doc, dist) in enumerate(zip(metadatas, documents, distances), start=1):
            preview = doc[:90].replace("\n", " ")
            print(f"  {rank}. [{meta['category']}] {meta['file_name']}  (distance={dist:.4f})")
            print(f"     {meta['relative_path']}")
            print(f"     {preview}")

        top_category = metadatas[0]["category"]
        matched = top_category in acceptable
        hits += matched
        print(f"  -> 1위 category={top_category!r} / 주제 부합: {'예' if matched else '아니오'}")
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="ChromaDB 임베딩 및 한국어 검색 검증")
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("student_dataset") / "file_metadata.csv",
        help="입력 file_metadata.csv 경로",
    )
    parser.add_argument("--db", type=Path, default=Path("./chroma_db"), help="ChromaDB 저장 경로")
    parser.add_argument("--limit", type=int, default=100, help="임베딩할 건수")
    parser.add_argument("--n-results", type=int, default=3, help="쿼리당 반환 건수")
    args = parser.parse_args()

    csv_path = args.csv.expanduser()
    if not csv_path.exists():
        print(f"[에러] CSV를 찾을 수 없습니다: {csv_path}", file=sys.stderr)
        return 1

    rows = load_success_rows(csv_path, args.limit)
    print(f"[입력] {csv_path.resolve()}")
    print(f"[선택] extraction_status == 'success' 상위 {len(rows)}건")
    if not rows:
        print("[에러] 임베딩할 행이 없습니다.", file=sys.stderr)
        return 1

    client = chromadb.PersistentClient(path=str(args.db))
    print(f"[DB] PersistentClient(path={args.db}) — 최초 실행 시 임베딩 모델을 내려받습니다.")

    collection = build_collection(client, rows)
    print(f"[임베딩] 컬렉션 {COLLECTION_NAME!r}에 {collection.count()}건 저장 완료")

    hits = run_queries(collection, args.n_results)

    print("\n" + "=" * 72)
    print(f"검색 품질 요약: 쿼리 {len(VERIFICATION_QUERIES)}건 중 {hits}건에서 1위 결과가 주제에 부합")
    if hits < len(VERIFICATION_QUERIES):
        print(
            "  기본 임베딩 모델(all-MiniLM-L6-v2)은 영어 중심이라 한국어 의미 검색 품질이 낮다.\n"
            "  -> 2주차 과제: BAAI/bge-m3 등 다국어 임베딩 모델로 교체 후 재평가."
        )
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
