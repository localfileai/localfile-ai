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
  /** "한 번에 모두 설치"가 받을 구성에 들어가는가 */
  planned: boolean;
  /** 현재 사용하도록 설정된 모델인가 */
  selected: boolean;
  approx_gb: number;
  purpose: string;
  detail: string;
  /** 모델 배포 라이선스 (ADR-0004) */
  license?: string;
  /** 상업적으로 써도 되는가. false면 유료화 시 별도 계약이 필요하다 */
  commercial?: boolean;
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
  /** 실패 갈래. 'runtime'이면 모델을 더 받아도 소용없고 Ollama를 다시 깔아야 한다 */
  error_kind?: FailureKind;
}

/**
 * 검색 모델이 안 되는 이유의 갈래. 화면이 "그래서 뭘 눌러야 하나"를 이걸로 정한다.
 *   runtime — Ollama 설치가 깨졌거나 낡았다. 다시 설치하는 것 말고는 방법이 없다.
 *   memory  — 이 PC 메모리로 못 올린다.
 *   missing — 모델 파일이 없다. 받으면 된다.
 *   offline — Ollama가 응답하지 않는다.
 */
export type FailureKind = 'runtime' | 'memory' | 'missing' | 'offline' | 'unknown' | '';

/**
 * 검색 모델이 이 PC에서 **실제로** 도는가.
 *
 * 이름이 `ollama list`에 있는 것과 도는 것은 다른 문제다. pull은 파일을 받아
 * 오기만 해서, 낡은 Ollama는 받기에 성공하고 임베딩만 500으로 죽는다.
 */
export interface EmbedHealth {
  usable: boolean;
  /** 안 될 때 사용자에게 그대로 보여 줄 이유 */
  detail: string;
  model: string;
  /** 안 되는 이유의 갈래 */
  kind?: FailureKind;
}

export interface SetupStatus {
  ollama: { running: boolean; binary_found: boolean; base_url: string; version?: string };
  hardware: Hardware;
  recommendation: {
    generate_model: string;
    reason: string;
    /** 이 PC에 받아 둘 구성 전부 (고사양이면 경량 모델도 포함) */
    plan?: string[];
    /** 그중 아직 안 받은 것 */
    pending?: string[];
  };
  selected_model: string;
  /** 실제 검색에 쓰이는 임베딩 모델 (예비 모델로 갈아탔으면 카탈로그와 다르다) */
  active_embed_model?: string;
  embed: EmbedHealth;
  models: SetupModel[];
  missing_required: string[];
  ready: boolean;
  download: DownloadProgress;
  index: { ready: boolean; detail?: string; user_documents?: number };
}

/** 준비 상태 조회. 백엔드가 아직 안 떴으면 null(=아직 모름)을 돌려준다. */
export const getSetupStatus = async (): Promise<SetupStatus | null> => {
  try {
    // 시간 제한이 없으면 요청 하나가 매달렸을 때 이걸 기다리는 흐름
    // (준비 자동 진행)이 통째로 굳는다 — 실패 화면에 버튼이 안 나타나던
    // 원인 후보였다. 못 받으면 null로 끝내고 다음 폴링이 다시 묻는다.
    //
    // 제한은 백엔드의 최악 응답 시간보다 길어야 한다. 8초로 잡았다가 백엔드
    // 최악(옛 구조에서 15초)이 더 길어서 모든 질문이 답 직전에 끊기는 사고가
    // 났다. 지금은 백엔드 쪽 확인들을 1.5초 제한으로 줄여 최악 ~4초고,
    // 여기는 그 4배 여유를 둔다.
    const response = await fetch(`${BASE_URL}/setup/status`, {
      signal: AbortSignal.timeout(15000),
    });
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
