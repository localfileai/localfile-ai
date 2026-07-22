"""
파일 또는 폴더에서 지원 문서의 텍스트를 추출해 터미널에 출력하는 스크립트입니다.

FastAPI를 띄우지 않고 전처리 로직만 빠르게 확인할 때 사용합니다.
예: python scripts/extract_first_page.py ./samples
"""

import sys
from pathlib import Path

# 스크립트를 `python scripts/...` 형태로 실행해도 app 패키지를 찾을 수 있게 합니다.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.fileops import extract_from_path


def main():
    """명령행 인자를 받아 추출 결과를 보기 좋게 출력합니다."""
    if len(sys.argv) < 2:
        print("Usage: python extract_first_page.py <file_or_dir>")
        sys.exit(1)

    path = Path(sys.argv[1])
    for item in extract_from_path(str(path)):
        # 폴더 입력 시 여러 파일 결과가 섞이지 않도록 파일별 구분선을 출력합니다.
        print(f"--- {item['path']} ---")
        if item["error"]:
            print(f"ERROR: {item['error']}\n")
        else:
            # 검색/임베딩에서 실제로 사용할 정규화 텍스트를 먼저 보여줍니다.
            print(f"{item['normalized_text']}\n")


if __name__ == "__main__":
    main()
