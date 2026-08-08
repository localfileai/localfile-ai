# 실험 006: /organize 전체 단계별 지연 계측

작성일: 2026-08-08

## 지난 코드의 한계

기존에는 전체 `elapsed_ms`만 있어 추출, 임베딩, 분류, RAG, LLM 중 실제 병목을
구분할 수 없었다. 실험 005의 속도 측정도 분류와 RAG가 미리 준비된 조건이었다.

## 변경 코드를 통한 보완점

`OrganizeResponse.stages_ms`를 추가하고 extract, embedding, classify, rag, llm,
other 시간을 누적한다. API 호환성을 위해 기본 빈 객체를 가진 추가 필드로 설계했다.

## 실제 결과

동일한 5페이지 PDF를 실제 `/organize` slim+RAG로 두 번 실행했다.

| 단계 | 첫 요청 | 두 번째 요청 |
|---|---:|---:|
| 추출 | 110ms | 2ms |
| 임베딩 | 4,727ms | 135ms |
| 분류 | 402ms | 0ms |
| RAG | 26ms | 2ms |
| LLM | 2,133ms | 463ms |
| 기타 준비 | 2,047ms | 2ms |
| 전체 | 9,448ms | 606ms |

첫 요청 병목은 임베딩 모델 적재였고, 두 번째 요청 병목은 LLM이었다.

## 보완 코드의 한계

단계 시간은 누적 wall time이며 CPU 사용량이나 Ollama 내부 model load/eval 시간을
분리하지 않는다. 여러 파일 요청은 파일별 값이 아니라 전체 누적값이다.

