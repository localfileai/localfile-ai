# @localfile-ai/contracts

프론트엔드가 쓰는 TypeScript 타입입니다. **직접 편집하지 마세요.**

`apps/server/app/contracts/`의 Pydantic 모델에서 생성됩니다.

```bash
python scripts/generate_contracts.py
```

## 왜 생성하나

같은 스키마를 Python과 TypeScript에 각각 손으로 쓰면 반드시 갈라집니다.
BE가 필드를 하나 추가하고 FE가 모르면, 컴파일은 통과하는데 런타임에
`undefined`가 나옵니다. 그리고 그 버그는 통합 단계에서야 발견됩니다.

Pydantic 모델을 단일 기준으로 두고 여기서 타입을 뽑으면 그 경로가 막힙니다.

## 언제 붙나

2주차. 계약이 안정된 뒤입니다.
지금 붙이면 스키마가 매일 바뀌면서 생성물 충돌만 늘어납니다.

그전까지 FE는 임시 타입을 각자 파일에 두고 `// TODO: contracts 생성으로 교체`를
남겨두세요. 이 디렉터리에는 넣지 않습니다.

## 계약을 바꾸려면

1. [계약 변경 제안 이슈](../../.github/ISSUE_TEMPLATE/contract.yml)를 엽니다
2. 영향받는 파트가 동의합니다
3. Pydantic 모델 수정 → 생성 스크립트 실행 → **생성물까지 같은 PR에** 커밋
4. CODEOWNERS가 4명 전원을 리뷰어로 지정합니다

자세한 내용은 [docs/data-contract.md](../../docs/data-contract.md).
