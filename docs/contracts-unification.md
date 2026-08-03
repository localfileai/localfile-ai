# 계약 단일화 제안 — `contracts/ai.py` ↔ `contracts/api.py`

- **작성**: 강인혁 (BE1) · 3주차
- **상태**: 제안 (BE2·FE 합의 필요 — 1주차부터 이월된 "2주차 최우선" 항목)

## 문제

같은 개념을 두 파일이 다르게 부른다. 심지어 **같은 이름의 클래스가 다른 모양**으로
두 파일에 존재한다 — import 실수 한 번이면 조용히 틀린 검증을 하게 된다.

| 위험 | `contracts/ai.py` (BE1 · 팀 공용) | `contracts/api.py` (BE2 · Mock API용) |
|---|---|---|
| ⚠️ 이름 충돌 1 | `SearchResponse` — query/total_hits/hits(score 0~1) | `SearchResponse` — count/items(score 0~100 int) |
| ⚠️ 이름 충돌 2 | `ApplyRequest` — approved(필수 True)+items+dry_run | `ApplyRequest` — ids 목록뿐 (**승인 개념 없음**) |
| 필드명 | `recommended_filename` | `recommended_name` / `next` |
| 필드명 | `reason` | `summary` |
| 단위 | `confidence` 0.0~1.0 | `confidence` 0~100 int |
| 파일 표현 | `FileRef` (path·name·extension·size·mtime) | name/ext/path 낱개 필드 |

FE(`src/api/organizeApi.ts`)는 현재 "어느 쪽이 와도 안 죽게" 모든 후보 필드를
optional로 열어 두고 골라 읽는다 — 계약이 계약 구실을 못 하고 있다는 뜻이다.

## 제안

**`ai.py`를 단일 기준으로 하고, `api.py`는 Mock 전용으로 격리 후 4주차에 제거한다.**

근거: 실제 런타임 경로가 이미 전부 `ai.py`를 쓴다.

| 경로 | 계약 |
|---|---|
| `GET /search` (실제 검색) | `ai.SearchResponse` |
| `POST /organize` (실제 추천) | `ai.OrganizeResponse` |
| `POST /index` (실제 색인) | `ai.IndexRequest` |
| `/mock/*` (1주차 하드코딩) | `api.py` — **여기만 남았다** |

`api.py`에서 실제로 계속 쓰이는 것은 전처리 계약(`ExtractPathRequest`,
`ExtractedDocument`, `ExtractPathResponse`)뿐이며, 이는 `ai.py`와 겹치지 않는다.

## 이행 계획 (파트별)

| 순서 | 담당 | 작업 |
|---|---|---|
| 1 | FE2 | `organizeApi.ts`를 `/mock/rename`·`/mock/move` 대신 `POST /organize`(`OrganizeResponse`)로 전환. Raw 타입의 optional 후보 필드 제거 |
| 2 | BE2 | 승인 API를 `ai.ApplyRequest`(approved 강제) 기준으로 작성 — 기획안 "사용자가 승인한 경우에만 실행"은 `api.ApplyRequest(ids)`로는 지킬 수 없다 |
| 3 | BE2 | `api.py`에서 Mock 전용 모델(`SearchResponse`·`Rename*`·`Move*`·`ApplyRequest`·`ApplyResponse`·`ReanalyzeResponse`)을 `mock.py` 라우터 파일 안으로 이동해 이름 충돌 제거. 전처리 계약 3종만 `api.py`에 유지 |
| 4 | FE 전환 완료 후 | `/mock/*` 라우터와 함께 Mock 모델 제거 (4주차 패키징 전) |

## 이행하면서 지켜야 할 변환 규칙 (FE 참고)

| Mock 필드 | 단일 계약 필드 | 변환 |
|---|---|---|
| `old` | `current.name` | — |
| `next` / `recommended_name` | `suggestion.recommended_filename` | — |
| `confidence` (0~100) | `suggestion.confidence` (0.0~1.0) | ×100 후 반올림해 표시 |
| `to` / `path` | `suggestion.recommended_folder` | 상대 경로 (분류 폴더 기준) |
| `summary` | `suggestion.reason` | — |
| `score` (0~100) | `hits[].score` (0.0~1.0) | ×100 후 반올림해 표시 |

## 결정 필요

이 문서는 제안이다. `api.py`와 FE 코드는 각각 BE2·FE2 소유라 BE1이 직접 바꾸지 않았다.
팀 회의에서 순서 1~4 합의 후 각자 진행하면 되고, 합의되면 이 문서를 ADR로 승격한다.
