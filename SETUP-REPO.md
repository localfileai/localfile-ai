# 저장소 세팅

한 번만 하면 되는 작업입니다. **BE1이 대표로 실행**하고 나머지는 클론만 하면 됩니다.

이 파일 자체는 세팅이 끝나면 지워도 됩니다.

---

## 0. gh CLI 설치

아래 명령 대부분이 GitHub CLI를 씁니다. 웹 화면에서 클릭해도 되지만
20분 걸릴 일이 2분에 끝납니다.

```powershell
winget install --id GitHub.cli
gh auth login
```

## 1. 저장소 생성

```powershell
cd C:\Users\IHK\localfile-ai

git init -b main
git add .
git commit -m "chore: 프로젝트 구조 및 개발 규칙 초기 설정"

gh repo create localfileai/localfile-ai `
    --private `
    --source . `
    --remote origin `
    --description "내 PC의 문서를 로컬에서 검색하고 정리하는 데스크톱 앱. Ollama + ChromaDB." `
    --push
```

> `--private`로 시작하는 걸 권합니다. 3주차쯤 앱이 동작하고 README에
> 데모 GIF가 붙었을 때 public으로 바꾸세요. 비어 있는 상태로 공개해두는 것보다
> 완성도가 있을 때 여는 편이 낫습니다.
>
> public 전환: `gh repo edit localfileai/localfile-ai --visibility public`

## 2. BE1 1주차 작업물 이관 — 완료됨

`localfile-ai-be1/`의 코드는 이미 옮겨져 있습니다. **원본 폴더는 그대로 뒀으니**
푸시가 끝나고 정상 동작을 확인한 뒤에 지우세요.

| 원본 | 옮겨진 곳 |
|---|---|
| `schemas.py` | `apps/server/app/contracts/schemas.py` — 실험이 아니라 팀 공용 계약이라 승격 |
| `schemas.py`의 `__main__` 자체 테스트 | `apps/server/tests/test_contracts.py` — pytest 17건으로 변환 |
| 나머지 `*.py`, `DATASET_CHANGES.md` | `apps/server/experiments/` |
| `README.md`의 실험 결과 | [ADR-0002](docs/decisions/0002-model-selection.md) |
| `.py.orig`, `venv/`, `chroma_db/`, 결과 CSV, `student_dataset/` | 옮기지 않음 |

실험 코드의 `from schemas import ...`는 `from app.contracts import ...`로 고쳤습니다.
`pip install -e .` 상태면 어디서 실행하든 import됩니다.

## 3. 팀원 초대

```powershell
gh api -X PUT /orgs/localfileai/memberships/lauranofirst1 -f role=member
gh api -X PUT /orgs/localfileai/memberships/hongham       -f role=member
gh api -X PUT /orgs/localfileai/memberships/0hj2          -f role=member
```

저장소 권한 (CODEOWNERS가 동작하려면 **write 이상**이어야 합니다):

```powershell
gh api -X PUT /repos/localfileai/localfile-ai/collaborators/lauranofirst1 -f permission=push
gh api -X PUT /repos/localfileai/localfile-ai/collaborators/hongham       -f permission=push
gh api -X PUT /repos/localfileai/localfile-ai/collaborators/0hj2          -f permission=push
```

## 4. 라벨

기본 라벨은 지우고 우리 것으로 채웁니다.

```powershell
# 기본 라벨 정리
"bug","documentation","duplicate","enhancement","good first issue","help wanted","invalid","question","wontfix" |
    ForEach-Object { gh label delete $_ --yes 2>$null }

# 파트
gh label create "part: be1" --color 0E8A16 --description "AI/DB · @InhyeokKang"
gh label create "part: be2" --color 1D76DB --description "파일 시스템/API · @lauranofirst1"
gh label create "part: fe1" --color 5319E7 --description "Electron 아키텍처 · @hongham"
gh label create "part: fe2" --color D93F0B --description "UI/UX · @0hj2"

# 유형
gh label create "type: feat"     --color A2EEEF --description "기능 추가"
gh label create "type: fix"      --color D73A4A --description "버그 수정"
gh label create "type: docs"     --color 0075CA --description "문서"
gh label create "type: exp"      --color FBCA04 --description "실험"
gh label create "type: contract" --color B60205 --description "계약 변경 — 전원 합의 필요"
gh label create "type: chore"    --color CFD3D7 --description "빌드·설정·의존성"

# 상태
gh label create "blocked"          --color 000000 --description "다른 작업에 막힘"
gh label create "needs discussion" --color E4E669 --description "구현 전 논의 필요"
```

## 5. 마일스톤

번다운이 자동으로 그려집니다. 주차를 라벨로 만들지 마세요.

```powershell
$m = @(
    @{ t="Week 1 · 데이터셋 확보 · Mock 연동";     d="2026-07-26" },
    @{ t="Week 2 · 모델 테스트 · 시스템 뼈대";     d="2026-08-02" },
    @{ t="Week 3 · 모델 최적화 · 파일 제어";       d="2026-08-09" },
    @{ t="Week 4 · 패키징 · 배포";                 d="2026-08-16" }
)
foreach ($x in $m) {
    gh api -X POST /repos/localfileai/localfile-ai/milestones `
        -f title="$($x.t)" -f due_on="$($x.d)T23:59:59Z"
}
```

2026-07-20(월) 시작 기준, 월~일 단위입니다.

## 6. main 브랜치 보호

**이걸 안 하면 나머지 규칙이 전부 권고사항이 됩니다.**

```powershell
gh api -X PUT /repos/localfileai/localfile-ai/branches/main/protection `
  --input - <<'JSON'
{
  "required_status_checks": null,
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "require_code_owner_reviews": true,
    "dismiss_stale_reviews": true
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true
}
JSON
```

> PowerShell에서 heredoc이 안 되면 위 JSON을 `protection.json`으로 저장하고
> `--input protection.json`을 쓰세요.

`required_status_checks`는 일단 `null`입니다. CI가 한 번이라도 돌아야
체크 이름이 등록됩니다. 첫 PR이 병합된 뒤 아래로 켜세요.

```powershell
gh api -X PATCH /repos/localfileai/localfile-ai/branches/main/protection/required_status_checks `
    -f strict=true -F 'contexts[]=check'
```

`enforce_admins`는 `false`로 뒀습니다. 4주 프로젝트에서 배포 직전에
관리자까지 막히면 곤란합니다. 대신 **쓰지 마세요.** 쓰는 순간 규칙이 무너집니다.

## 7. 병합 방식

squash만 허용합니다. `main` 히스토리가 PR 단위로 깔끔하게 남습니다.

```powershell
gh repo edit localfileai/localfile-ai `
    --enable-squash-merge `
    --enable-merge-commit=false `
    --enable-rebase-merge=false `
    --delete-branch-on-merge
```

## 8. 프로젝트 보드

```powershell
gh project create --owner localfileai --title "LocalFile AI"
```

컬럼은 `Backlog → This Week → In Progress → In Review → Done` 정도면 충분합니다.
칸반을 정교하게 만들 시간에 이슈를 쓰는 게 낫습니다.

## 9. 조직 프로필 README

이 저장소와 **별개**입니다. `.github`라는 이름의 **public** 저장소가 따로 필요합니다.

`C:\Users\IHK\localfileai-org-profile\`에 준비돼 있습니다.
[그쪽 SETUP.md](../localfileai-org-profile/SETUP.md)를 보세요.

---

# 진행이 보이게 만들기

구조를 잘 잡아도 커밋이 몰아치기로 들어가면 4주 내내 아무 일도 없다가
마지막에 폭발한 것처럼 보입니다. 아래는 **실제 작업을 그대로 드러내는** 방법입니다.

## 커밋을 몰지 않는다

가장 큰 차이를 만드는 건 이것 하나입니다.

| | |
|---|---|
| ❌ | 사흘 작업하고 `feat: 검색 기능 구현` 한 방에 1,200줄 |
| ✅ | 하루에 2~4개 커밋. `feat(rag): ChromaDB 컬렉션 초기화` → `feat(rag): 유사도 검색 쿼리` → `test(rag): 상위 N건 정렬 검증` |

기능이 완성돼야 커밋하는 게 아닙니다. **논리적 단위가 끝나면** 커밋합니다.
작업 브랜치의 커밋은 squash되므로 지저분해도 괜찮습니다.

PR은 하루에 하나씩 여는 걸 목표로 하세요. 400줄이 넘으면 쪼갭니다.

## Conventional Commits

`main` 히스토리가 그 자체로 개발 일지가 됩니다.

```
feat(rag): bge-m3로 임베딩 모델 교체
fix(fileops): 파일이 열려 있을 때 앱이 멈추는 문제
test(llm): ValidationError 재시도 경로 검증
docs(adr): 모노레포 결정 기록 추가
```

`git log --oneline`만 봐도 4주간 무엇이 있었는지 읽힙니다.

## 주차별 태그와 릴리스

```powershell
git tag -a v0.2.0 -m "Week 2: 실제 LLM·DB 연동"
git push origin v0.2.0
gh release create v0.2.0 --generate-notes --title "v0.2.0 · Week 2"
```

자동 생성 노트 맨 위에 **그 주에 무엇이 가능해졌는지** 두세 줄을 직접 쓰세요.
커밋 목록만 있으면 아무도 읽지 않습니다.

```markdown
Mock 데이터를 걷어내고 실제 Ollama와 ChromaDB를 붙였습니다.
폴더를 선택하면 진짜로 문서를 읽고 추천을 냅니다.

한국어 검색은 임베딩 모델을 bge-m3로 바꾼 뒤 상위 1건 정확도가 3/10 → 8/10.
```

## 주차 기록

[docs/weekly/](docs/weekly/)에 주가 끝날 때마다 씁니다. 30분 안에.

"알게 된 것" 항목이 핵심입니다. 1주차의 라벨 규칙 결함 발견 같은 것 —
**계획대로 안 된 일과 거기서 뭘 배웠는지**가 계획대로 된 일보다 더 많은 걸 말해줍니다.

## ADR

되돌리기 어려운 결정은 [docs/decisions/](docs/decisions/)에 남깁니다.
"왜 exaone인가"에 실측 표로 답하는 문서가 있는 것과 없는 것은 차이가 큽니다.

## 이슈 먼저

이슈 없이 커밋하지 마세요. 이슈 → 브랜치 → PR → 병합이 이어지면
GitHub이 자동으로 타임라인을 만들어줍니다. 나중에 "이건 왜 이렇게 됐지"를
역추적할 수 있는 유일한 경로이기도 합니다.

## 데모 GIF

3주차에 앱이 동작하면 README 상단에 넣으세요.
**README에서 가장 효과가 큰 한 칸입니다.** 스크린샷 한 장이 문단 열 개보다 낫습니다.

Windows는 [ScreenToGif](https://www.screentogif.com/)가 편합니다.
`docs/assets/demo.gif`에 두고 README에서 참조하세요. 10초 안쪽, 5MB 이하로.

---

# 다음에 만들 것

지금 구조에 비어 있는 것들입니다. 필요할 때 채우세요.

- [ ] `apps/desktop/` — FE1이 `npm create vite@latest`로 생성.
      손으로 만든 스캐폴드보다 정확합니다. 생성 후 `electron/`과 `src/`로 나누세요
- [ ] `scripts/generate_contracts.py` — 2주차, 계약이 안정된 뒤
- [ ] `.github/workflows/release.yml` — 4주차, Windows 러너에서 electron-builder 패키징
- [ ] `apps/server/.env.example` — 환경 변수가 확정되면
