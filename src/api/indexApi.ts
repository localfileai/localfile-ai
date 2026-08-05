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
  failed: { path: string; reason: string }[];
  error?: string;
  finished_at?: string;
}

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
