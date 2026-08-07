# 4주차 — 승인 후 실제 파일 변경 · server.exe 준비 · 웜업 (BE1)

> 작업 브랜치: `claude/be1-week-3-tasks-peajyw` (3주차와 같은 브랜치에 이어서)
> 전제: 3주차에서 모델 선정 마감(qwen3-embedding:0.6b + exaone3.5:7.8b/2.4b),
> 분류 3방식 통합, 실파일 검증(86.7%)까지 완료된 상태.

## 계획서 4주차 항목 대비

| 계획서 4주차 항목 | 담당 | 결과 |
|---|---|---|
| 승인 → 실제 파일 이동/개명 (기술 챌린지: 충돌 검사·경로 검증·작업 이력) | BE2 몫이나 부재 → BE1이 구현 (리뷰 필요) | ✅ `POST /apply` + 이력 + 되돌리기 |
| 파일 사용 중·권한 에러에도 안 뻗기 | BE1&2 | ✅ apply의 파일 단위 격리 |
| 텍스트 청킹 길이 조절 | BE1&2 | ✅ 이미 반영분 문서화 (아래 참고) |
| server.exe 빌드 (PyInstaller) | BE1&2 | ✅ 빌드 사양·스크립트·frozen 경로 (빌드 실행은 Windows) |
| 검색 웜업 (3주차 개선안 C 이월) | BE1 | ✅ 서버 시작 시 백그라운드 웜업 |
| 로딩 바·에러 모달·Setup.exe | FE1&2 | 범위 밖 — 단, apply 실패 사유는 FE alert까지 전달되게 연결함 |

---

## 1. 승인 후 실제 파일 변경 — `POST /apply` (기능④)

기획안 원칙 그대로: **AI는 제안만 하고, 파일은 사용자가 승인한 뒤에만 바뀐다.**
계약(`contracts/ai.py`)의 `ApplyRequest`가 `approved=True`를 강제하고(거짓이면
422로 요청 자체가 거부), 실행은 새 모듈 `app/fileops/apply.py`가 맡는다.

### 안전장치 (기획안 기술 챌린지 대응)

| 장치 | 동작 | 실패 시 |
|---|---|---|
| 경로 탈출 금지 | 원본·대상 모두 root(정리 대상 폴더) 안이어야 함. `..`·절대 경로로 밖을 가리키면 거부 | 그 항목만 `failed: unsafe_path` |
| 충돌 검사 | 대상에 같은 이름 파일이 있으면 **덮어쓰지 않고** 건너뜀 | `skipped: conflict` |
| 확장자 보존 | 개명으로 확장자가 바뀌는 요청은 거부 (문서가 열리지 않게 되는 사고 방지) | `failed: extension_mismatch` |
| 권한 에러 격리 | Windows에서 파일이 열려 있으면 `PermissionError` — **그 항목만 실패**하고 나머지는 계속 진행 | `failed: permission` |
| dry_run | `dry_run=true`면 검증만 하고 파일은 안 건드림 — FE가 "몇 건 적용 가능한지" 미리 보여줄 때 사용 | `valid` |

### 작업 이력 + 되돌리기

- 실제로 옮긴 내역은 `apply_history/<이력ID>.json`에 남는다 (`{from, to}` 목록)
- `GET /apply/history` — 최근 작업 목록 (FE '정리 내역' 화면용)
- `POST /apply/undo` — 가장 최근(또는 지정) 작업을 **역순으로** 복원.
  원래 자리에 새 파일이 생겼으면 그 항목만 건너뛰고 이유를 남긴다 (apply와 같은 격리 원칙).
  같은 작업을 두 번 되돌릴 수는 없다.

### FE 연결 (mock → 실제)

`src/api/organizeApi.ts`의 적용 함수 2개가 `/mock/*/apply` 대신 실제 `/apply`를 호출한다:

- **파일명 변경 적용**: 파일은 제자리에 두고 이름만 추천안으로 (`target_folder` = 현재 위치)
- **폴더 이동 적용**: 이름은 그대로 두고 추천 폴더로만 이동
- `analyzeFolder`가 분석 결과(원본 절대 경로·추천값)를 캐시해 두고, 적용 성공분은
  캐시를 새 경로로 갱신한다 — **개명 후 이동**(또는 반대)을 이어서 해도 경로가 안 낡는다
- 폴더를 선택하지 않은 데모 상태에서는 기존 mock 적용으로 폴백 (1주차 데모 유지)
- `OrganizedView`의 알림이 정직해졌다: 무조건 "성공"이 아니라
  **실제 적용 건수 + 적용 안 된 항목별 사유**(충돌·권한 등)를 보여주고,
  성공한 항목만 목록에서 사라진다

> **BE2·FE2 리뷰 필요**: apply API는 원래 BE2 몫(부재로 BE1이 구현),
> `OrganizedView.tsx` 알림 로직은 FE2 소유 코드를 수정했다.

## 2. 텍스트 청킹 길이 — 이미 반영된 결정의 문서화

계획서의 "청크 길이 조절" 항목은 3주차 작업에서 사실상 결정돼 있었다:

- **추출 단계**: 첫 페이지/앞부분 중심 최대 2,000자 (`extraction/service.py`) —
  분류·추천에 필요한 건 문서 주제이지 전문이 아니다
- **임베딩 단계**: `INDEX_EMBED_MAX_CHARS=800` (`core/config.py`) —
  임베딩 시간은 글자 수에 비례하므로 이 값이 저사양 색인 속도를 직접 좌우한다.
  800자로도 주제 판별에 충분함은 3주차 분류 실측(실파일 86.7%)이 뒷받침한다
- 검색 발췌(`matched_text`)는 계약 상한 500자라 800자 임베딩과 안 부딪힌다

문서를 여러 청크로 쪼개 전부 임베딩하는 방식(진짜 청킹)은 **일부러 안 한다**:
파일당 임베딩 횟수가 곱절로 늘어 저사양 색인이 느려지고, 우리 용도(파일 단위
분류·검색)에서는 문서당 좌표 1개면 충분하다는 것이 실측 결론이다.

## 3. server.exe 패키징 준비 (PyInstaller)

빌드 자체는 Windows에서 해야 하므로(PyInstaller는 실행한 OS용 실행 파일을 만든다),
이번 주 산출물은 **빌드가 되는 상태**까지다:

- `backend/run.py` — 실행 파일 엔트리. uvicorn에 앱 객체를 직접 넘긴다
  (frozen 환경에서 문자열 import·reload·워커 스폰이 동작하지 않기 때문).
  `multiprocessing.freeze_support()`로 Windows 자식 프로세스 무한 재실행 방지
- `backend/server.spec` — 빌드 사양. chromadb·uvicorn·fitz·olefile을 `collect_all`로
  통째로 포함 (동적 import라 정적 분석에 안 잡힘). 실험 전용 패키지는 제외
- **frozen 경로 처리** — `core/config.py`의 `BASE_DIR`:
  onefile 실행 파일의 `__file__`은 종료 시 삭제되는 임시 폴더(`_MEIPASS`)를
  가리키므로, 색인(`chroma_db`)·작업 이력(`apply_history`)을 거기 두면
  재시작마다 사라진다. frozen이면 **실행 파일 옆 폴더**를 기준으로 잡는다
- `npm run backend:build-exe` — PyInstaller 설치부터 빌드까지 한 번에

Ollama와 모델은 실행 파일에 포함하지 않는다 — 사용자 PC에 별도 설치(기획안 전제).

## 4. 검색 웜업 (개선안 C)

첫 검색이 느린 이유는 검색이 아니라 준비 비용이다: Ollama 임베딩 모델 로드(~2초),
ChromaDB HNSW 색인 열기, 분류 라벨 정의문 9건의 좌표 계산.

`app/core/warmup.py` — 서버 시작 직후 데몬 스레드가 이 셋을 미리 치른다:

1. ChromaDB 색인 열기 (Ollama 없어도 가능)
2. 라벨 정의문 임베딩 → 모델 로드와 라벨 좌표 캐시가 한 호출로 해결

- 서버 기동은 안 막는다. Ollama가 꺼져 있으면 조용히 건너뛰고, 이유는 첫 요청의 503이 전달
- 테스트에서는 `LOCAL_FILE_AI_WARMUP=0`으로 끔 (conftest)
- 효과: 첫 검색이 워밍업 후 실측치(0.2초대)로 시작한다 — 3주차 벤치마크 [B] 참고

## 테스트

`tests/test_apply.py` 17건 추가 — 안전장치가 본체인 모듈이라 테스트도 안전장치 중심:
실제 임시 폴더에서 이동·개명, dry_run 무변경, 충돌 건너뜀, root 탈출 거부(원본·대상 모두),
확장자 변경 거부, **권한 에러 시 그 항목만 실패하고 나머지 진행**, undo 역순 복원,
undo 자리 점유 시 건너뜀, 이중 undo 거부, API 왕복(apply→history→undo), 미승인 422.

```
81 passed   (3주차 64 + apply 17)
tsc --noEmit 통과 (FE 타입 검사)
```

## 실기기에서 확인할 것 (Windows)

```bash
# 1) server.exe 빌드 — dist/server.exe가 생기고 더블클릭으로 서버가 뜨는지
npm run backend:build-exe

# 2) 실제 적용 흐름 — 앱에서 폴더 선택 → 추천 → 체크 → 적용:
#    파일이 실제로 이동/개명되는지, 열려 있는 파일은 사유와 함께 실패로 뜨는지
npm run backend:dev  &  npm run dev

# 3) 되돌리기
curl -X POST http://127.0.0.1:8000/apply/undo
```

## 미해결 (이월)

- 팀원 2주차 결과물 통합 판정 (수령 대기) — 관건: BE2 apply 존재 여부.
  BE2 것이 오면 이번 `/apply`와 비교해 하나로 합쳐야 한다 (계약은 이미 `ai.py` 단일 기준)
- FE 로딩 UI(FE1&2 몫) — 백엔드의 색인 진행률 API(`GET /index/status`)는 준비돼 있음
- admin 카테고리 합성 데이터 하락(100→67%) 관찰 항목 유지 (실파일에서는 문제없음)
- undo의 FE 노출 (버튼) — API는 있으니 FE2와 화면 위치 협의
