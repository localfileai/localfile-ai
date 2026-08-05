/**
 * 첫 실행 준비 API — 계약: backend/app/api/routes/setup.py
 *
 * 사용자가 터미널에서 `ollama pull`을 치는 대신 앱이 대신 받아 준다.
 */

const BASE_URL = 'http://127.0.0.1:8000';

export interface SetupModel {
  name: string;
  role: 'embed' | 'generate_slim' | 'generate_full';
  required: boolean;
  present: boolean;
  approx_gb: number;
  purpose: string;
}

export interface DownloadProgress {
  running: boolean;
  model: string;
  phase: string;
  percent: number;
  overall: number;
  done: string[];
  error: string;
}

export interface SetupStatus {
  ollama: { running: boolean; binary_found: boolean; base_url: string };
  models: SetupModel[];
  missing_required: string[];
  ready: boolean;
  download: DownloadProgress;
  index: { ready: boolean; detail?: string; user_documents?: number };
}

/** 준비 상태 조회. 백엔드가 아직 안 떴으면 null(=아직 모름)을 돌려준다. */
export const getSetupStatus = async (): Promise<SetupStatus | null> => {
  try {
    const response = await fetch(`${BASE_URL}/setup/status`);
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
};

/** 없는 모델을 받기 시작한다. includeFull=true면 고품질 7.8b까지. */
export const startModelDownload = async (includeFull = false): Promise<string> => {
  const response = await fetch(`${BASE_URL}/setup/models?include_full=${includeFull}`, {
    method: 'POST',
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.detail || `다운로드를 시작할 수 없습니다 (HTTP ${response.status})`);
  }
  return body?.started ? '' : (body?.detail ?? '');
};
