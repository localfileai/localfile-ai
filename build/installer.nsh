; 설치·제거 전에 실행 중인 앱을 정리한다.
;
; 왜 필요한가: 앱을 켜 둔 채로 제어판에서 제거하면 창이 그대로 남고,
; 그 상태에서는 파일이 잠겨 있어 재설치도 실패한다.
; 백엔드(server.exe)는 앱이 띄운 자식 프로세스라 함께 정리해야 한다.

!macro killLocalFileAI
  nsExec::Exec 'taskkill /f /im "LocalFile AI.exe" /t'
  nsExec::Exec 'taskkill /f /im "server.exe" /t'
  ; 파일 잠금이 풀릴 시간을 잠깐 준다
  Sleep 800
!macroend

!macro customInit
  !insertmacro killLocalFileAI
!macroend

!macro customUnInit
  !insertmacro killLocalFileAI
!macroend

!macro customUnInstall
  !insertmacro killLocalFileAI
!macroend
