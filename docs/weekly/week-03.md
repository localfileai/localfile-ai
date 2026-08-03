# 3주차 — 모델 최적화 · 추천 경로 실제 연결 · 검증/재시도 (BE1)

- **작성**: 강인혁 (BE1 · AI/DB)
- **기준 브랜치**: `week1-integration` 위에 작업
- **작업 환경**: 클라우드 세션 (Ollama·색인 없음 → 코드/테스트/문서만. 실기기 측정은 아래 "로컬에서 돌릴 것" 참고)

## 계획서 3주차 BE1 항목 대비

| 계획서 항목 | 상태 |
|---|---|
| 유사도 검색 API 구현 | 2주차 선행 구현 완료(`GET /search`) → 3주차에 **지연 최적화** 적용 |
| 답변 생성 속도·품질을 위한 전반적인 모델 최적화 | **코드 완료** — 커넥션 재사용 + `keep_alive`, RAG·k-NN 단일 질의, slim 모드. 수치 측정은 로컬 실기기 필요 |
| Pydantic 에러 검증 및 재시도 로직 | **완료** — 확장자 자동 보정 + 위반 제약 명시 1회 재시도. 테스트 25건 |

2주차 이월분인 **추천 경로 연결**(`/mock/*` 하드코딩 → 실제 RAG+LLM)도 이번에 구현했다: `POST /organize`.

## 새로 생긴 것

```
backend/app/
├─ core/config.py        Ollama·모델 설정 단일 출처 (ADR-0002 §3 후속 조치)
├─ llm/
│  ├─ client.py          Ollama generate 클라이언트 (Session 재사용 · keep_alive)
│  ├─ prompts.py         full/slim 프롬프트 · 위반 목록 포맷 · 재시도 프롬프트
│  └─ suggest.py         ★ 검증 + 1회 재시도 파이프라인 ★
├─ rag/retrieve.py       유사 예시 + k-NN 분류를 임베딩 질의 한 번으로 조회
└─ api/routes/organize.py  POST /organize · GET /organize/status
backend/tests/           25건 — LLM·컬렉션을 가짜로 주입해 Ollama 없이 돈다
```

- 계약 추가: `contracts/ai.py`에 `OrganizeRequest` (path · mode · max_files · use_rag). 자체 테스트 26→30건
- `npm run backend:test` 추가

## `POST /organize` — 실제 추천 경로

```
추출(BE2 extraction) → RAG 조회 → LLM 생성 → 검증+재시도 → OrganizeResponse
```

```jsonc
// 요청
{ "path": "C:/Users/me/Downloads", "mode": "full", "max_files": 20, "use_rag": true }
// 응답: contracts/ai.py의 OrganizeResponse (FE '미리보기 표' 데이터)
```

- 파일 변경은 하지 않는다. 승인 후 이동/이름 변경은 계획서상 BE2의 apply API 몫
- Ollama·모델이 없으면 503 + 이유 (`GET /organize/status`로 사전 확인 가능)
- 파일 단위 실패는 억지 추천 없이 `failed[]`에 이유와 함께 남긴다

### 검증 + 재시도 (ADR-0002가 exaone 채택의 전제 조건으로 못박은 것)

1. **확장자 자동 보정** — exaone의 유일한 대량 탈락 원인(1차 측정 JSON 유효율 62.5%)이
   확장자 누락이었다. 원본 확장자는 백엔드가 아는 값이라 후처리로 붙인다. 재시도보다 먼저 적용되므로
   이 사례는 **LLM 재호출 없이** 해결된다 (CPU에서 호출당 수십 초 절약).
2. **위반 명시 1회 재시도** — 그래도 `FileSuggestion` 검증에 실패하면 "어느 필드가 어떤 제약을
   어겼는지"를 이전 출력과 함께 보여 주고 정확히 1회 재시도한다. 또 실패하면 `failed[]`로.

## 모델 최적화 (계획서 3주차 항목)

| 조치 | 근거 | 기대 효과 |
|---|---|---|
| `requests.Session` 재사용 + `keep_alive: 10m` (임베딩·생성 공통) | ADR-0002 §5: 질의 지연의 96%가 요청당 고정 오버헤드, GPU·모델 축소로 안 줄어듦 | 검색 체감 지연 감소 (실기기 측정 필요) |
| RAG 예시 + k-NN 분류를 **임베딩 질의 한 번**으로 | CPU 질의당 약 2.8초 → 두 번 질의하면 두 배 | 추천 파일당 임베딩 비용 절반 |
| **slim 모드** (`mode: "slim"`) — 분류는 k-NN(k=3, 96.0%), LLM은 파일명만(2.4b) | ADR-0002 §5-1: 81.1초 → 13.0초/파일 | GPU 없는 PC 대응 |
| 설정 단일화 (`core/config.py`) | ADR-0002 §3 "설정 한 곳에 모을 것" | 모델 교체 실험이 env 변수 하나 |

slim 모드는 **2.4b 파일명 품질 재측정 전이라 기본값이 아니다** (`LOCAL_FILE_AI_RECOMMEND_MODE`로 변경 가능).

## 테스트

```
npm run backend:test        # 25건, Ollama 불필요
```

- 재시도: 정상 응답은 재시도 없음 / 확장자 누락은 보정으로 해결(재호출 없음) /
  위반 시 위반 필드가 재시도 프롬프트에 포함 / 재시도 실패 시 이유와 함께 실패 / 재시도는 정확히 1회
- slim 조립: k-NN 분류 + 파일명 합성, 금지 문자 재시도
- retrieve: 단일 질의로 예시+투표, 자기 자신 제외, 계약 밖 카테고리 무시
- API: 503(모델 없음) · 400(경로 오류) · 422(모르는 mode) · full/slim 정상 경로 · failed 분리

## ⚠️ 로컬 PC(Ollama 있는 곳)에서 돌릴 것

클라우드 세션이라 실행 측정을 못 했다. 전부 `backend/`에서:

```powershell
# ① RAG 효과 측정 (2주차 이월 — ADR-0002 §6 재검토 조건)
.venv\Scripts\python.exe scripts\test_models.py --sample 40 --seed 42 --autofix-extension
.venv\Scripts\python.exe scripts\test_models.py --sample 40 --seed 42 --autofix-extension --with-rag

# ② 재시도 효과 측정 (이번에 추가된 --retry 옵션, 요약에 "재시도 n건 중 m건 구제" 출력)
.venv\Scripts\python.exe scripts\test_models.py --sample 40 --seed 42 --retry

# ③ exaone3.5:2.4b 품질 재측정 (slim 채택 여부 결정)
.venv\Scripts\python.exe scripts\test_models.py --sample 40 --seed 42 --autofix-extension --models exaone3.5:2.4b exaone3.5:7.8b

# ④ 실제 추천 API 동작 확인 (서버는 npm run backend:dev 로)
curl -X POST http://127.0.0.1:8000/organize -H "Content-Type: application/json" ^
     -d "{\"path\": \"C:/Users/blues/Documents/테스트폴더\", \"max_files\": 3}"
curl http://127.0.0.1:8000/organize/status
```

①의 판단 기준: ADR-0002가 잡은 목표 구간 "관례 제공 시 20%→70%" 사이 어디에 떨어지는지.
③의 판단 기준: 파일명 점수·학기 포함률·한국어 유지율이 7.8b 대비 얼마나 빠지는지 (ADR-0002 §5-1).

## 미해결 (이월)

- **계약 이원화** — `contracts/ai.py`(BE1) vs `contracts/api.py`(BE2). `/organize`는 ai.py를 쓰지만
  FE의 `organizeApi.ts`는 아직 `/mock/*` 필드명 기준. FE 바인딩(FE2 3주차 항목)과 함께 정리 필요
- **FE 연결** — `/organize` 응답을 미리보기 표에 바인딩하는 것은 FE2 3주차 항목. 승인 후 apply API는 BE2
- **Ollama 직렬 처리** — 색인·검색·추천이 서로를 막는 문제. 큐 분리 미착수
- **브랜치 구조** — `main`(모노레포) vs `week1-integration`(플랫). 머지 전 팀 논의 필요 (ADR-0001)
- k-NN 실전 정확도 / Drag & Drop 동작 확인 (기존 이월 항목 유지)
