/**
 * 폴더 색인 API — 계약: backend/app/api/routes/indexing.py
 *
 * 검색이 동작하려면 문서가 먼저 색인돼야 한다. 사용자가 그걸 알 필요는 없으므로
 * 폴더를 고르면 앱이 알아서 색인을 시작하고 진행률만 보여 준다.
 */

const BASE_URL = 'http://127.0.0.1:8000';

export interface IndexProgress {
  running: boolean;
  path: string;
  total: number;
  done: number;
  skipped: number;
  /** done + skipped. 진행 바는 이 값으로 그려야 한다 (증분 색인에서 done은 잘 안 오른다) */
  processed: number;
  elapsed_sec: number;
  /** 남은 시간(초). 속도가 잡히기 전에는 null */
  eta_sec: number | null;
  /** 마지막으로 색인한 폴더. 앱을 다시 켤 때 이 폴더로 돌아간다 */
  last_root: string;
  failed: { path: string; reason: string }[];
  error?: string;
  finished_at?: string;
}

/** 남은 시간을 사람이 읽는 문구로. */
export const formatEta = (seconds: number | null): string => {
  if (seconds === null || seconds < 0) return '';
  if (seconds < 60) return `약 ${Math.max(1, Math.round(seconds))}초 남음`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `약 ${minutes}분 남음`;
  return `약 ${Math.floor(minutes / 60)}시간 ${minutes % 60}분 남음`;
};

/** 색인을 시작한다. 이미 돌고 있으면(409) 조용히 넘어간다 — 진행률로 확인된다. */
export const startIndexing = async (path: string): Promise<string> => {
  try {
    const response = await fetch(`${BASE_URL}/index`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    });
    if (response.status === 409) return '';
    if (!response.ok) {
      const detail = (await response.json().catch(() => null))?.detail;
      return typeof detail === 'string' ? detail : `색인을 시작할 수 없습니다 (HTTP ${response.status})`;
    }
    return '';
  } catch {
    return '백엔드에 연결할 수 없습니다.';
  }
};

export const fetchIndexProgress = async (): Promise<IndexProgress | null> => {
  try {
    const response = await fetch(`${BASE_URL}/index/status`);
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
};
