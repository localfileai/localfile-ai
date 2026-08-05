/**
 * 첫 실행 준비 API — 계약: backend/app/api/routes/setup.py
 *
 * 사용자가 터미널에서 `ollama pull`을 치는 대신 앱이 대신 받아 준다.
 */

const BASE_URL = 'http://127.0.0.1:8000';

export interface SetupModel {
  name: string;
  role: 'embed' | 'generate';
  /** generate 모델의 등급. light = 경량, standard = 표준 */
  tier: '' | 'light' | 'standard';
  label: string;
  required: boolean;
  present: boolean;
  /** 이 PC 사양에 권장되는가 */
  recommended: boolean;
  /** 현재 사용하도록 설정된 모델인가 */
  selected: boolean;
  approx_gb: number;
  purpose: string;
  detail: string;
}

export interface Hardware {
  os: string;
  cpu_cores: number;
  ram_gb: number;
  gpu_name: string;
  vram_gb: number;
  has_usable_gpu: boolean;
  summary: string;
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
  hardware: Hardware;
  recommendation: { generate_model: string; reason: string };
  selected_model: string;
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

/**
 * 고른 모델을 받기 시작한다. 목록을 비우면 이 PC에 권장되는 구성을 받는다.
 * 받기로 한 생성 모델이 그대로 사용 모델이 된다.
 */
export const startModelDownload = async (models: string[] = []): Promise<string> => {
  const response = await fetch(`${BASE_URL}/setup/models`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ models }),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.detail || `다운로드를 시작할 수 없습니다 (HTTP ${response.status})`);
  }
  return body?.started ? '' : (body?.detail ?? '');
};

/** 이미 받아 둔 모델 중에서 사용할 것을 바꾼다. */
export const selectModel = async (model: string): Promise<void> => {
  const response = await fetch(`${BASE_URL}/setup/select`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model }),
  });
  if (!response.ok) {
    const detail = (await response.json().catch(() => null))?.detail;
    throw new Error(detail || `모델을 바꿀 수 없습니다 (HTTP ${response.status})`);
  }
};
