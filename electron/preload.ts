import { ipcRenderer, contextBridge, webUtils } from 'electron'

// --------- Expose some API to the Renderer process ---------
contextBridge.exposeInMainWorld('ipcRenderer', {
  on(...args: Parameters<typeof ipcRenderer.on>) {
    const [channel, listener] = args
    return ipcRenderer.on(channel, (event, ...args) => listener(event, ...args))
  },
  off(...args: Parameters<typeof ipcRenderer.off>) {
    const [channel, ...omit] = args
    return ipcRenderer.off(channel, ...omit)
  },
  send(...args: Parameters<typeof ipcRenderer.send>) {
    const [channel, ...omit] = args
    return ipcRenderer.send(channel, ...omit)
  },
  invoke(...args: Parameters<typeof ipcRenderer.invoke>) {
    const [channel, ...omit] = args
    return ipcRenderer.invoke(channel, ...omit)
  },

  // You can expose other APTs you need here.
  // ...
})

/**
 * 드롭된 File에서 로컬 실제 경로를 뽑는다.
 *
 * `webUtils.getPathForFile`이 권장 방식이지만, contextBridge를 건너온 File은
 * 상황에 따라 내부 조회에 실패해 **예외를 던지거나 빈 문자열을 돌려줍니다.**
 * 그대로 두면 호출부에서 map이 통째로 터지고 아무 일도 일어나지 않은 것처럼 보입니다.
 *
 * 그래서 두 단계로 방어합니다.
 *   1) webUtils.getPathForFile        — Electron 30+ 권장
 *   2) File.path                      — 구 방식. Electron 30에는 아직 남아 있고 32에서 제거됨
 * 둘 다 실패하면 빈 문자열을 돌려주고 호출부가 사용자에게 알립니다.
 */
function resolveDroppedPath(file: File): string {
  try {
    const resolved = webUtils.getPathForFile(file)
    if (resolved) return resolved
    console.warn('[preload] webUtils.getPathForFile이 빈 문자열을 반환했습니다.')
  } catch (error) {
    console.error('[preload] webUtils.getPathForFile 실패:', error)
  }

  const legacyPath = (file as File & { path?: string }).path
  if (legacyPath) {
    console.warn('[preload] File.path 폴백을 사용했습니다 (Electron 32에서 제거됨).')
    return legacyPath
  }

  console.error('[preload] 드롭된 항목의 경로를 확인할 수 없습니다:', file.name)
  return ''
}

// --------- 앱 전용 API (폴더 선택 IPC + 드롭 파일 경로 추출 + 첫 실행 준비) ---------
contextBridge.exposeInMainWorld('api', {
  // 메인 프로세스에 폴더 선택 창을 요청하고 경로를 받는다.
  selectFolder: (): Promise<string | null> =>
    ipcRenderer.invoke('dialog:openDirectory'),
  // 드롭된 File 객체에서 로컬 실제 경로를 추출한다.
  getPathForFile: (file: File): string => resolveDroppedPath(file),

  // 파일이 있는 폴더를 탐색기로 열고 그 파일을 선택해 준다.
  revealFile: (filePath: string): Promise<boolean> =>
    ipcRenderer.invoke('shell:revealFile', filePath),

  // 5주차: 백엔드(server.exe)를 앱이 직접 띄우므로 그 상태를 화면에 알린다.
  backendStatus: () => ipcRenderer.invoke('backend:status'),
  onBackendState: (listener: (state: unknown) => void) => {
    const handler = (_event: unknown, state: unknown) => listener(state)
    ipcRenderer.on('backend:state', handler)
    return () => ipcRenderer.off('backend:state', handler)
  },

  // Ollama 자동 설치 (진행률은 onOllamaProgress로 흘러온다).
  // { repair: true }를 주면 이미 떠 있어도 설치본을 덮어씌운다 — 응답은 하는데
  // 모델 실행 파일이 빠져 있는 설치를 되돌리는 유일한 방법이다.
  installOllama: (options?: { repair?: boolean }) =>
    ipcRenderer.invoke('setup:installOllama', options),
  onOllamaProgress: (listener: (progress: unknown) => void) => {
    const handler = (_event: unknown, progress: unknown) => listener(progress)
    ipcRenderer.on('setup:ollamaProgress', handler)
    return () => ipcRenderer.off('setup:ollamaProgress', handler)
  },
})
