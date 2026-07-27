# 저장소 세팅 — 완료 기록

초기 세팅은 끝났습니다. 이 파일은 무엇이 어떻게 설정돼 있는지에 대한 기록입니다.
새로 합류하는 사람은 [CONTRIBUTING.md](CONTRIBUTING.md)와
[docs/development.md](docs/development.md)를 보세요.

## 적용된 설정

| 항목 | 상태 |
|---|---|
| 공개 여부 | **public** — 무료 플랜에서 브랜치 보호를 쓰려면 public이어야 합니다 |
| 기본 브랜치 | `main` |
| `main` 보호 | 직접 푸시 차단, PR 리뷰 1건 필수, CODEOWNERS 리뷰 필수, 리뷰 후 새 커밋 시 승인 무효화, 대화 해결 필수, force push·삭제 금지 |
| 병합 방식 | squash only. merge commit·rebase 비활성. 병합 후 브랜치 자동 삭제 |
| CI | `server` / `desktop` 경로 필터 워크플로 |
| 라벨 | 파트 4 · 유형 6 · 상태 2 |
| 마일스톤 | Week 1(종료) ~ Week 4 |

### 일부러 안 켠 것

**필수 상태 검사(required status checks).** 켜지 않았습니다. 켜면 PR이 영영
병합되지 않습니다.

워크플로에 경로 필터가 걸려 있어서, 서버만 고친 PR에서는 `desktop` 워크플로가
아예 실행되지 않습니다. 그런데 필수 상태 검사는 **실행되지 않은 검사를
"대기 중"으로 간주하고 병합을 막습니다.** 모노레포에서 흔히 밟는 함정입니다.

굳이 켜야 한다면 항상 실행되는 게이트 잡을 하나 만들어 그것만 필수로 지정하세요.
4주 규모에서는 리뷰어가 빨간 CI를 보고 판단하는 것으로 충분합니다.

**`enforce_admins`.** 껐습니다. 배포 직전에 관리자까지 막히면 곤란해서입니다.
대신 **쓰지 마세요.** 쓰는 순간 규칙이 무너집니다.

### 알아둘 것

리뷰 1건이 필수라 **자기 PR을 자기가 병합할 수 없습니다.** 팀원 중 한 명의
승인이 반드시 필요합니다. 의도한 동작이지만, 급할 때 막힐 수 있습니다.
그럴 때 관리자 권한으로 우회하지 말고 팀원에게 리뷰를 요청하세요.

## 통합된 저장소

| 원래 | 지금 |
|---|---|
| `local-file-ai-backend` | `apps/server/` — 12커밋 히스토리째 병합. **아카이브됨** |
| `local-file-ai-frontend` | `apps/desktop/` 에서 진행 예정. 비어 있었음. **아카이브됨** |
| `Project-Overview` | `docs/` . **아카이브됨** |
| `localfile-ai-be1` (로컬) | `apps/server/experiments/` + `app/contracts/` |
| `Dataset` | **그대로 둡니다.** 이 저장소가 public이 됐으므로 데이터는 private에 있어야 합니다 |

아카이브는 되돌릴 수 있습니다: `gh repo unarchive localfileai/<이름>`

`local-file-ai-backend`의 `mock/pdf/` TSN 논문 9건(24MB)은 가져오지 않았습니다.
public 저장소에 저널 논문을 재배포하게 되기 때문입니다. 원본은 아카이브된
저장소에 그대로 있습니다.

## 남은 작업

- [ ] **FE1 GitHub 핸들 확인.** [CODEOWNERS](.github/CODEOWNERS)에 `@hongham`으로
      적혀 있는데 조직 멤버가 아닙니다. 대신 `@kimyunzoo`가 멤버입니다.
      조직 멤버가 아닌 계정은 CODEOWNERS에서 무시되고, `apps/desktop/electron/`에
      대한 리뷰어 자동 지정이 동작하지 않습니다
- [ ] `apps/desktop/` — FE1이 `npm create vite@latest`로 생성
- [ ] `scripts/generate_contracts.py` — 계약이 하나로 합쳐진 뒤 (#5)
- [ ] `.github/workflows/release.yml` — 4주차, Windows 러너에서 electron-builder
- [ ] `apps/server/.env.example` — 환경 변수 확정 후

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

## 주차별 태그와 릴리스

```powershell
git tag -a v0.2.0 -m "Week 2: 실제 LLM·DB 연동"
git push origin v0.2.0
gh release create v0.2.0 --generate-notes --title "v0.2.0 · Week 2"
```

자동 생성 노트 맨 위에 **그 주에 무엇이 가능해졌는지** 두세 줄을 직접 쓰세요.
커밋 목록만 있으면 아무도 읽지 않습니다.

## 주차 기록

[docs/weekly/](docs/weekly/)에 주가 끝날 때마다 씁니다. 30분 안에.

"알게 된 것" 항목이 핵심입니다. 1주차의 라벨 규칙 결함 발견 같은 것 —
**계획대로 안 된 일과 거기서 뭘 배웠는지**가 계획대로 된 일보다 더 많은 걸 말해줍니다.

## 이슈 먼저

이슈 없이 커밋하지 마세요. 이슈 → 브랜치 → PR → 병합이 이어지면
GitHub이 자동으로 타임라인을 만들어줍니다.

## 데모 GIF

3주차에 앱이 동작하면 README 상단에 넣으세요.
**README에서 가장 효과가 큰 한 칸입니다.**

Windows는 [ScreenToGif](https://www.screentogif.com/)가 편합니다.
`docs/assets/demo.gif`에 두고 10초 안쪽, 5MB 이하로.
