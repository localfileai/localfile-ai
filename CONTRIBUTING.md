# 기여 가이드

4주 안에 4명이 하나의 앱을 만듭니다. 규칙은 최소한으로 두되, 지키는 건 확실히 합니다.

## 원칙 세 가지

1. **`main`은 항상 실행된다.** 깨진 상태로 두지 않습니다. 언제 체크아웃해도 앱이 뜹니다.
2. **PR은 작게, 자주.** 한 PR이 400줄을 넘으면 리뷰가 형식적으로 변합니다. 쪼개세요.
3. **계약을 먼저 합의한다.** API 스키마가 바뀌면 3명이 영향을 받습니다. 코드보다 먼저 이슈로 논의합니다.

## 브랜치

```
main                          보호됨. 항상 빌드 가능. 직접 푸시 금지
└── <type>/<part>-<요약>      작업 브랜치. PR로만 병합
```

| 예시 | |
|---|---|
| `feat/be1-bge-m3-embedding` | 기능 추가 |
| `fix/fe2-preview-table-overflow` | 버그 수정 |
| `refactor/be2-extraction-module` | 동작 변경 없는 구조 개선 |
| `docs/adr-llm-selection` | 문서 |
| `chore/ci-python-314` | 빌드·설정·의존성 |
| `exp/be1-rag-ablation` | 실험. 병합하지 않고 결과만 문서로 남길 수 있음 |

`<part>`는 `be1` `be2` `fe1` `fe2` `ai` 중 하나입니다.
브랜치 목록만 봐도 누가 뭘 하는지 보입니다.

**develop 브랜치는 두지 않습니다.** 4주 프로젝트에서 릴리스 브랜치를 관리하는 비용이
얻는 것보다 큽니다. 주차별 태그로 대신합니다.

## 커밋 메시지

[Conventional Commits](https://www.conventionalcommits.org/)를 따릅니다.

```
<type>(<scope>): <한 줄 요약>

<본문 — 왜 이렇게 했는지. 무엇을 했는지는 diff에 있습니다>

Refs: #12
```

**type** — `feat` `fix` `refactor` `perf` `test` `docs` `chore` `exp`

**scope** — `desktop` `electron` `ui` `server` `api` `rag` `llm` `extraction`
`watcher` `fileops` `db` `contracts` `ci`

```
feat(rag): all-MiniLM에서 bge-m3로 임베딩 모델 교체

한국어 쿼리에서 distance가 0.85~1.18 구간에 뭉쳐 변별이 되지 않았다.
bge-m3로 교체 후 동일 쿼리 10건에서 상위 1건 정확도 3/10 → 8/10.

Refs: #23
```

요약은 한국어로 씁니다. 팀 전원이 한국어를 쓰는데 영어로 적으면 정확도만 떨어집니다.
`type`과 `scope`는 도구가 읽으므로 영어를 유지합니다.

### 커밋 단위

하나의 커밋은 **하나의 논리적 변경**입니다. 작업 중 자유롭게 커밋하고,
PR 병합 시 squash되므로 `main` 히스토리는 PR 단위로 깔끔하게 남습니다.

`wip`, `수정`, `ㅇㅇ` 같은 메시지는 작업 브랜치에서는 괜찮지만
**PR 제목은 반드시 규칙을 따르세요.** squash 후 그것이 `main`의 커밋 메시지가 됩니다.

## Pull Request

### 절차

1. 이슈를 먼저 만듭니다. 이슈 없는 PR은 나중에 왜 그랬는지 추적이 안 됩니다.
2. 브랜치를 파고 작업합니다.
3. PR을 엽니다. 제목은 커밋 규칙과 동일하게, 본문은 템플릿을 채웁니다.
4. CODEOWNERS가 리뷰어를 자동 지정합니다.
5. **승인 1개 + CI 통과** 후 squash merge.

### 리뷰

- **24시간 안에 응답합니다.** 못 볼 것 같으면 미리 말해주세요. 4주짜리에서 하루는 큽니다.
- 승인하지 않고 코멘트만 남기는 건 괜찮습니다. 다만 무엇이 막고 있는지는 명확히 적으세요.
- 취향 차이는 `nit:` 접두어를 붙입니다. 붙었으면 반영하지 않아도 병합 가능합니다.

### 작업 중 PR

이틀 이상 걸리는 작업은 **초안(Draft) PR을 먼저 여세요.** 방향이 어긋난 걸
사흘 뒤에 발견하는 것보다 낫습니다.

## 계약 변경

`apps/server/app/contracts/`는 백엔드·프론트엔드가 함께 쓰는 단일 기준입니다.

1. **[계약 변경 제안 이슈](../../issues/new?template=contract.yml)를 먼저 엽니다.**
2. 영향받는 파트가 이슈의 체크박스로 동의합니다.
   CODEOWNERS는 전원을 리뷰어로 요청하지만 GitHub이 강제하는 건 1명의 승인뿐입니다.
   **전원 합의는 이 체크박스가 유일한 기록입니다.**
3. Pydantic 모델을 고치고 `npm run contracts:generate`로 TypeScript 타입을 재생성합니다.
4. PR에는 생성된 타입도 함께 커밋합니다. CI가 최신 여부를 검사합니다.

**TypeScript 인터페이스를 손으로 다시 쓰지 마세요.** 백엔드와 프론트엔드가
조용히 갈라지는 가장 흔한 경로입니다.

## 이슈와 라벨

| 종류 | 라벨 |
|---|---|
| 파트 | `part: be1` `part: be2` `part: fe1` `part: fe2` `part: ai` |
| 유형 | `type: feat` `type: fix` `type: docs` `type: exp` `type: contract` `type: chore` |
| 상태 | `blocked` `needs discussion` `good first issue` |

주차는 라벨 대신 **마일스톤**을 씁니다 (`Week 1` ~ `Week 4`).
번다운 차트가 자동으로 그려집니다.

## 릴리스

주차가 끝나면 `main`에 태그를 답니다.

```bash
git tag -a v0.2.0 -m "Week 2: 실제 LLM·DB 연동"
git push origin v0.2.0
```

| 태그 | 시점 |
|---|---|
| `v0.1.0` | 1주차 — Mock 프로토타입 |
| `v0.2.0` | 2주차 — 실제 LLM·DB 연동 |
| `v0.3.0` | 3주차 — 파일 제어 전체 사이클 |
| `v1.0.0` | 4주차 — `setup.exe` 배포 |

GitHub Release는 자동 생성 노트를 쓰되, 맨 위에 **그 주에 무엇이 가능해졌는지**
두세 줄을 직접 적으세요. 커밋 목록만 있으면 아무도 읽지 않습니다.

## 실험 기록

BE1의 모델·임베딩 실험처럼 결과가 **판단 근거**가 되는 작업은 코드만 남기면 안 됩니다.

- 실험 코드는 `apps/server/experiments/`
- 무엇을 왜 측정했고 어떤 결론을 내렸는지는 `docs/decisions/`에 ADR로
- 수치는 재현 가능해야 합니다. seed, 표본 수, 모델 버전을 기록하세요

실험은 **한 번에 하나씩** 돌립니다. 동시에 돌리면 GPU 경합으로 응답 시간이
2배 이상 왜곡됩니다. 정확도는 영향받지 않지만 지표 하나가 못 쓰게 됩니다.

## 로컬 검사

PR을 올리기 전에 돌려보세요. CI에서 도는 것과 같습니다.

```bash
# 서버
cd apps/server
ruff check . && ruff format --check . && pytest -q

# 데스크톱
cd apps/desktop
npm run lint && npm run typecheck && npm run build
```
