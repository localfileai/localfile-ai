/**
 * 사용자 피드백 — 계약: backend/app/api/routes/feedback.py
 *
 * 잘못 분류된 파일에 올바른 갈래를 알려 주면, 그 예시가 쌓여 다음부터는
 * 그 사람의 관례에 맞춰 분류된다. 모델을 다시 학습시키는 게 아니라
 * 참고 자료가 늘어나는 구조라 저사양에서도 비용이 없다.
 */

const BASE_URL = 'http://127.0.0.1:8000';

/** 백엔드 Category와 같은 값. 화면에는 한글 이름을 보여 준다. */
export const CATEGORIES: { value: string; label: string }[] = [
  { value: 'lecture', label: '강의자료' },
  { value: 'assignment', label: '과제' },
  { value: 'report', label: '실험·보고서' },
  { value: 'reference', label: '참고자료' },
  { value: 'project', label: '프로젝트' },
  { value: 'exam_prep', label: '시험 준비' },
  { value: 'career', label: '취업·진로' },
  { value: 'admin', label: '행정 서류' },
  { value: 'personal', label: '개인' },
  { value: 'etc', label: '기타' },
];

export const categoryLabel = (value: string): string =>
  CATEGORIES.find((entry) => entry.value === value)?.label ?? value;

/** 이 파일의 올바른 갈래를 알려 준다. 다음 분류부터 반영된다. */
export const sendFeedback = async (path: string, category: string): Promise<void> => {
  const response = await fetch(`${BASE_URL}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, category }),
  });
  if (!response.ok) {
    const detail = (await response.json().catch(() => null))?.detail;
    throw new Error(detail || `저장하지 못했습니다 (HTTP ${response.status})`);
  }
};
