import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import SetupGate from './components/SetupGate.tsx'
import SettingsPanel from './components/SettingsPanel.tsx'
import { applyTheme, readTheme } from './theme'
import './index.css'

// 화면이 그려지기 전에 테마를 적용한다 — 어두운 테마인데 흰 화면이 한 번
// 번쩍이는 것을 막는다.
applyTheme(readTheme())

// 5주차: AI 엔진(백엔드)과 모델이 준비되기 전에는 준비 화면을 보여 준다.
// 준비가 끝난 사용자는 이 화면을 거치지 않고 바로 App으로 들어간다.
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <SetupGate>
      <App />
      {/* 설정은 어느 화면에서나 오른쪽 아래 버튼으로 연다 */}
      <SettingsPanel />
    </SetupGate>
  </React.StrictMode>,
)

// Use contextBridge
window.ipcRenderer?.on('main-process-message', (_event, message) => {
  console.log(message)
})
