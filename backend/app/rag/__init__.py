"""벡터 검색 (BE1 · 기능① 자연어 파일 검색).

BE1이 1주차에 선정한 임베딩 모델 `bge-m3`로 질의를 벡터화하고,
`scripts/embed_dataset.py`가 만든 ChromaDB 컬렉션에서 유사 문서를 찾는다.

역할 분담
  - 색인(쓰기) : `scripts/embed_dataset.py`  ← BE1 1주차 산출물 ①②
  - 검색(읽기) : 이 패키지                    ← 같은 컬렉션을 읽는다

계획서 기준으로 "Ollama 모델과 ChromaDB 연동"은 2주차 BE1 항목이다.
1주차 Mock(`/mock/search`)은 그대로 남겨 두고 이쪽을 따로 붙였다.
"""
