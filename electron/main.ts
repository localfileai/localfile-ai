import { app, BrowserWindow, ipcMain, dialog, Menu } from 'electron'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import {
  getBackendState,
  onBackendState,
  startBackend,
  stopBackend,
} from './backend'
import { installOllama } from './ollama'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// The built directory structure
//
// ├─┬─┬ dist
// │ │ └── index.html
// │ │
// │ ├─┬ dist-electron
// │ │ ├── main.js
// │ │ └── preload.mjs
// │
process.env.APP_ROOT = path.join(__dirname, '..')

// 🚧 Use ['ENV_NAME'] avoid vite:define plugin - Vite@2.x
export const VITE_DEV_SERVER_URL = process.env['VITE_DEV_SERVER_URL']
export const MAIN_DIST = path.join(process.env.APP_ROOT, 'dist-electron')
export const RENDERER_DIST = path.join(process.env.APP_ROOT, 'dist')

process.env.VITE_PUBLIC = VITE_DEV_SERVER_URL ? path.join(process.env.APP_ROOT, 'public') : RENDERER_DIST

let win: BrowserWindow | null

function createWindow() {
  // 기본 메뉴(File/Edit/View/Window/Help)는 Electron이 붙여 주는 것이고
  // 이 앱에는 쓸 항목이 없다. 설정은 화면 안의 설정 버튼으로 연다.
  Menu.setApplicationMenu(null)

  win = new BrowserWindow({
    // 창·작업 표시줄 아이콘. 설치본의 실행 파일 아이콘은 build/icon.ico를 쓴다.
    icon: path.join(process.env.VITE_PUBLIC, 'app-icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.mjs'),
    },
  })

  // Test active push message to Renderer-process.
  win.webContents.on('did-finish-load', () => {
    win?.webContents.send('main-process-message', (new Date).toLocaleString())
    // 화면이 준비된 뒤에 현재 백엔드 상태를 한 번 밀어 준다.
    // (창이 뜨기 전에 상태가 바뀌었을 수 있다)
    win?.webContents.send('backend:state', getBackendState())
  })

  if (VITE_DEV_SERVER_URL) {
    win.loadURL(VITE_DEV_SERVER_URL)
  } else {
    // win.loadFile('dist/index.html')
    win.loadFile(path.join(RENDERER_DIST, 'index.html'))
  }
}

// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
    win = null
  }
})

// 앱이 꺼질 때 백엔드도 반드시 함께 정리한다.
// 남으면 포트를 붙잡아 다음 실행이 "이미 떠 있는 서버"에 붙어 버린다.
app.on('before-quit', stopBackend)
app.on('will-quit', stopBackend)

app.on('activate', () => {
  // On OS X it's common to re-create a window in the app when the
  // dock icon is clicked and there are no other windows open.
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow()
  }
})

app.whenReady().then(() => {
  // OS 네이티브 폴더 선택 창을 여는 IPC 핸들러.
  // 렌더러(window.api.selectFolder)에서 호출 → 선택된 폴더 경로 반환(취소 시 null).
  ipcMain.handle('dialog:openDirectory', async () => {
    const result = win
      ? await dialog.showOpenDialog(win, { properties: ['openDirectory'] })
      : await dialog.showOpenDialog({ properties: ['openDirectory'] })
    if (result.canceled || result.filePaths.length === 0) return null
    return result.filePaths[0]
  })

  // 백엔드 상태를 렌더러가 물어보거나(invoke) 구독할 수 있게 한다(event).
  ipcMain.handle('backend:status', () => getBackendState())
  onBackendState((next) => win?.webContents.send('backend:state', next))

  // Ollama 자동 설치. 진행률은 이벤트로 흘려 준비 화면이 그린다.
  ipcMain.handle('setup:installOllama', async () => {
    return installOllama((progress) => win?.webContents.send('setup:ollamaProgress', progress))
  })

  createWindow()

  // 창을 먼저 띄우고 백엔드를 붙인다 — 사용자는 검은 화면 대신
  // "AI 엔진을 시작하는 중" 안내를 보게 된다.
  void startBackend()
})
