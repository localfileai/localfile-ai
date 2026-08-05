/// <reference types="vite-plugin-electron/electron-env" />

declare namespace NodeJS {
  interface ProcessEnv {
    /**
     * The built directory structure
     *
     * ```tree
     * ├─┬─┬ dist
     * │ │ └── index.html
     * │ │
     * │ ├─┬ dist-electron
     * │ │ ├── main.js
     * │ │ └── preload.js
     * │
     * ```
     */
    APP_ROOT: string
    /** /dist/ or /public/ */
    VITE_PUBLIC: string
  }
}

/** 앱이 띄운 백엔드의 상태 (electron/backend.ts) */
interface BackendState {
  status: 'starting' | 'ready' | 'failed' | 'external'
  detail: string
}

/** Ollama 설치 진행 상황 (electron/ollama.ts) */
interface OllamaInstallProgress {
  phase: 'downloading' | 'installing' | 'ready' | 'opened-page' | 'failed'
  percent: number
  detail: string
}

// Used in Renderer process, expose in `preload.ts`
interface Window {
  ipcRenderer: import('electron').IpcRenderer
  api: {
    /** OS 네이티브 폴더 선택 창을 열고 경로를 반환(취소 시 null) */
    selectFolder: () => Promise<string | null>
    /** 드롭된 File의 로컬 실제 경로 추출 */
    getPathForFile: (file: File) => string

    /** 앱이 띄운 백엔드(server.exe)의 현재 상태 */
    backendStatus: () => Promise<BackendState>
    /** 백엔드 상태 변화 구독. 반환값을 호출하면 구독 해제 */
    onBackendState: (listener: (state: BackendState) => void) => () => void

    /** Ollama 자동 설치를 시작한다 */
    installOllama: () => Promise<OllamaInstallProgress>
    /** Ollama 설치 진행률 구독. 반환값을 호출하면 구독 해제 */
    onOllamaProgress: (listener: (progress: OllamaInstallProgress) => void) => () => void
  }
}
