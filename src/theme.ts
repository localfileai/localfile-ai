/**
 * 화면 테마 (라이트/다크) — 설정에서 바꾸고 앱을 다시 켜도 유지된다.
 *
 * Tailwind v4는 기본적으로 OS 설정(prefers-color-scheme)을 따르는데, 그러면
 * 사용자가 앱 안에서 고를 수가 없다. index.css에서 `.dark` 클래스 기준으로
 * 바꿔 두고, 여기서 그 클래스를 문서 루트에 붙였다 뗀다.
 */

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'localfile-ai:theme';

export const readTheme = (): Theme => {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved === 'light' || saved === 'dark') return saved;
  // 처음 실행이면 OS 설정을 따른다
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
};

export const applyTheme = (theme: Theme): void => {
  document.documentElement.classList.toggle('dark', theme === 'dark');
  localStorage.setItem(STORAGE_KEY, theme);
};
