"""로컬 LLM 연동. (BE1)

Ollama로 exaone3.5:7.8b를 호출해 카테고리·폴더·파일명을 판단합니다.
fallback은 qwen2.5:7b (선정 근거는 docs/decisions/0002-model-selection.md).

호출 규칙
- format: json, temperature 0.1
- 응답은 반드시 contracts의 Pydantic 모델로 검증
- ValidationError 발생 시 위반한 제약을 프롬프트에 명시해 1회 재시도
  (exaone3.5는 reason 200자 초과·Enum 밖 값을 5.6% 확률로 냅니다. 필수입니다.)
"""
