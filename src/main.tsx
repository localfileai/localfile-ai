import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import SetupGate from './components/SetupGate.tsx'
import './index.css'

// 5주차: AI 엔진(백엔드)과 모델이 준비되기 전에는 준비 화면을 보여 준다.
// 준비가 끝난 사용자는 이 화면을 거치지 않고 바로 App으로 들어간다.
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <SetupGate>
      <App />
    </SetupGate>
  </React.StrictMode>,
)

// Use contextBridge
window.ipcRenderer?.on('main-process-message', (_event, message) => {
  console.log(message)
})
