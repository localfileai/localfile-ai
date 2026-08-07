"""기능②③ Pydantic 검증 + 재시도 로직 동작 시연 (BE1 3주차 산출물).

계획서 3주차: "로컬 LLM이 가끔 형식이 깨진 응답을 반환할 때를 대비한
Pydantic 에러 검증 및 재시도 로직 추가" — 그 로직이 실제로 무엇을 하는지
**깨진 응답 사례별로 전 과정을 출력**한다.

사례는 지어낸 게 아니라 1주차 실험에서 실제로 관찰된 실패 유형이다 (ADR-0002).
LLM 호출부만 대본(scripted)으로 바꿔 끼웠고, 보정·검증·재시도 코드는
런타임(`app/llm/suggest.py`)과 완전히 같은 것을 실행한다. Ollama가 필요 없다.

실행:  python scripts/demo_retry.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.llm.suggest import suggest_full

FILE = dict(
    current_name="최종.pdf",
    current_path="C:/Users/student/Downloads",
    extension="pdf",
    first_page_text="데이터베이스 정규화 과제. 제3정규형까지 분해하는 과정을 정리한다...",
)

GOOD = {
    "category": "assignment",
    "recommended_folder": "assignment/데이터베이스/2025-1",
    "recommended_filename": "데이터베이스_정규화_과제_2025-1.pdf",
    "confidence": 0.87,
    "reason": "문서 유형이 과제로 명시되어 있고 과목은 데이터베이스이다.",
}

# (제목, [1차 응답, 2차 응답], 실제 관찰 출처)
CASES = [
    (
        "확장자 누락 — 1주차 exaone 탈락 15건 전부의 원인 (ADR-0002 1차 측정)",
        [json.dumps({**GOOD, "recommended_filename": "데이터베이스_정규화_과제_2025-1"},
                    ensure_ascii=False)],
        "기대: 재시도 없이 후처리(autofix)로 해결 — LLM 재호출 0회",
    ),
    (
        "허용 밖 category — enum에 없는 'homework'",
        [json.dumps({**GOOD, "category": "homework"}, ensure_ascii=False),
         json.dumps(GOOD, ensure_ascii=False)],
        "기대: 위반 필드를 명시한 재시도 1회로 구제",
    ),
    (
        "범위 밖 confidence(1.5) + 절대 경로 폴더 — 복수 위반",
        [json.dumps({**GOOD, "confidence": 1.5, "recommended_folder": "C:/정리"},
                    ensure_ascii=False),
         json.dumps(GOOD, ensure_ascii=False)],
        "기대: 위반 2건이 모두 재시도 프롬프트에 표시되고 1회로 구제",
    ),
    (
        "JSON이 아님 — 마크다운 코드펜스로 감싼 응답",
        ["```json\n" + json.dumps(GOOD, ensure_ascii=False) + "\n```",
         json.dumps(GOOD, ensure_ascii=False)],
        "기대: json_invalid 위반으로 재시도 1회로 구제",
    ),
    (
        "재시도해도 깨짐 — 두 번 다 잘못된 응답",
        [json.dumps({**GOOD, "category": "숙제"}, ensure_ascii=False),
         json.dumps({**GOOD, "category": "과제물"}, ensure_ascii=False)],
        "기대: 억지 추천을 만들지 않고 이유와 함께 실패(FailedFile 경로) — 재시도는 1회뿐",
    ),
]


def scripted(responses: list[str]):
    """대본대로 응답하는 가짜 LLM. 프롬프트를 기록해 재시도 내용을 보여 준다."""
    calls: list[dict] = []

    def generate(system: str, prompt: str) -> str:
        calls.append({"prompt": prompt})
        return responses[min(len(calls) - 1, len(responses) - 1)]

    generate.calls = calls
    return generate


def main() -> int:
    print("=" * 86)
    print("Pydantic 검증 + 1회 재시도 — 실제 실패 유형 5가지 재현")
    print(f"대상 파일: {FILE['current_name']}  ({FILE['current_path']})")
    print("=" * 86)

    ok = 0
    for index, (title, responses, expectation) in enumerate(CASES, start=1):
        print(f"\n[사례 {index}] {title}")
        print(f"  {expectation}")

        generate = scripted(responses)
        result = suggest_full(generate, **FILE)

        print(f"  1차 응답        : {responses[0][:76]}")
        if result.extension_fixed:
            print("  후처리          : 확장자 자동 보정 적용 (.pdf)")
        if result.retried:
            retry_prompt = generate.calls[-1]["prompt"]
            marker = "[재시도]"
            excerpt = retry_prompt[retry_prompt.index(marker):] if marker in retry_prompt else retry_prompt
            # 위반 내역 부분만 발췌해 보여 준다.
            lines = [l for l in excerpt.splitlines() if l.startswith(("- ", "[재시도]", "위반"))]
            print("  재시도 프롬프트 :")
            for line in lines[:6]:
                print(f"    {line}")
            print(f"  LLM 호출 수     : {len(generate.calls)}회 (재시도 1회 포함)")
        else:
            print(f"  LLM 호출 수     : {len(generate.calls)}회 (재시도 없음)")

        if result.suggestion is not None:
            s = result.suggestion
            print(f"  ✅ 최종 결과    : {s.category.value} / {s.recommended_folder} / "
                  f"{s.recommended_filename}")
            ok += 1
        else:
            print(f"  ❌ 실패 처리    : {result.error}")
            # 사례 5는 실패가 정답이다.
            ok += "재시도해도" in title

    print("\n" + "=" * 86)
    print(f"{ok}/{len(CASES)} 사례가 기대대로 동작")
    print("같은 코드가 POST /organize 안에서 실행된다. 재시도 1회로도 안 되면")
    print("억지 추천 대신 OrganizeResponse.failed[] 에 이유가 남는다.")
    print("=" * 86)
    return 0 if ok == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
