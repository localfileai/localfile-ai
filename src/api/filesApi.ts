/**
 * 폴더 안의 문서 목록 — 계약: backend/app/api/routes/files.py
 *
 * 목록을 그리는 데 텍스트 추출은 필요 없다. 예전에는 이 화면을 위해 모든
 * 파일의 첫 페이지를 추출하느라 파일이 많은 폴더에서 몇 분씩 멈춰 있었다.
 */

const BASE_URL = 'http://127.0.0.1:8000';

export interface FolderFile {
  path: string;
  name: string;
  extension: string;
  /** 고른 폴더 기준 상대 폴더. 바로 아래면 빈 문자열 */
  folder: string;
  size_bytes: number;
  modified_at: string;
}

export const listFolderFiles = async (
  path: string,
): Promise<{ items: FolderFile[]; total: number; error: string }> => {
  try {
    const response = await fetch(`${BASE_URL}/files?path=${encodeURIComponent(path)}`);
    if (!response.ok) {
      const detail = (await response.json().catch(() => null))?.detail;
      return { items: [], total: 0, error: detail || `목록을 읽지 못했습니다 (HTTP ${response.status})` };
    }
    const data = await response.json();
    return { items: data.items ?? [], total: data.total ?? 0, error: '' };
  } catch {
    return { items: [], total: 0, error: '백엔드에 연결할 수 없습니다.' };
  }
};
