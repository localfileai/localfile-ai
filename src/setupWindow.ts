/**
 * 준비 화면을 어디서든 다시 여는 통로.
 *
 * 준비가 끝난 사용자는 SetupGate를 지나쳐 본 화면으로 들어간다. 그런데 나중에
 * 모델을 다시 받거나 Ollama를 고쳐야 할 일이 생기고, 그때 설정 패널에는 그
 * 화면으로 가는 길이 없었다 — "설정 버튼을 눌러도 모델 설치 화면이 안 뜬다"가
 * 그 상황이다.
 *
 * 설정 패널은 SetupGate의 **자식**이라 상태를 위로 올릴 수 없다. 상태 관리
 * 라이브러리를 들이는 대신 이벤트 하나로 잇는다.
 */

const EVENT = 'localfile-ai:open-setup';

/** 준비 화면을 연다. */
export function openSetupScreen(): void {
  window.dispatchEvent(new Event(EVENT));
}

/** 준비 화면 열기 요청을 구독한다. 반환값을 호출하면 해제된다. */
export function onOpenSetupScreen(listener: () => void): () => void {
  window.addEventListener(EVENT, listener);
  return () => window.removeEventListener(EVENT, listener);
}
