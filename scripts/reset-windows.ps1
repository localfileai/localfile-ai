<#
.SYNOPSIS
  이 PC를 "앱을 한 번도 깔지 않은 상태"로 되돌린다 (Windows 전용, 개발·테스트용).

.DESCRIPTION
  새 PC에서의 첫 설치 경험을 고치고 나면 그것을 확인할 새 PC가 필요하다.
  매번 남의 PC를 빌릴 수는 없으므로, 내 PC를 새 PC처럼 만드는 스크립트를 둔다.

  지우는 것은 -Scope로 고른다.

    models   AI 모델 파일만 (%USERPROFILE%\.ollama\models)
             Ollama는 그대로 둔다. "모델 다운로드"만 다시 보고 싶을 때.

    app      이 앱의 데이터만 (색인·설정·적용 이력)
             모델은 그대로 둔다. 색인·검색만 처음부터 다시 볼 때. 제일 빠르다.

    all      Ollama 제거 + 모델 전부 + 앱 데이터 + (선택) 앱 자체
             진짜 새 PC 상태. 다시 준비하는 데 수 GB 다운로드가 필요하다.

.PARAMETER Scope
  models | app | all  (기본값: app — 가장 안전한 쪽)

.PARAMETER RemoveApp
  -Scope all 일 때 LocalFileAI 앱 자체도 제거한다.

.PARAMETER Yes
  확인 질문을 건너뛴다. 지우는 스크립트라 기본은 물어본다.

.EXAMPLE
  # 색인·설정만 날리고 다시 (모델 유지 — 몇 초)
  powershell -ExecutionPolicy Bypass -File scripts\reset-windows.ps1 -Scope app

.EXAMPLE
  # 진짜 새 PC 상태로 (앱까지 제거)
  powershell -ExecutionPolicy Bypass -File scripts\reset-windows.ps1 -Scope all -RemoveApp

.NOTES
  ⚠️ -Scope models / all 은 **이 PC의 Ollama 모델을 전부** 지운다.
     다른 프로젝트에서 받아 둔 모델이 있으면 그것도 함께 사라진다.
     `ollama list`로 먼저 확인할 것.
#>
[CmdletBinding()]
param(
    [ValidateSet('models', 'app', 'all')]
    [string]$Scope = 'app',
    [switch]$RemoveApp,
    [switch]$Yes
)

$ErrorActionPreference = 'Stop'

function Write-Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Write-Done($text) { Write-Host "   $text" -ForegroundColor DarkGray }

function Get-FolderSizeGb($path) {
    if (-not (Test-Path $path)) { return 0 }
    $bytes = (Get-ChildItem $path -Recurse -File -ErrorAction SilentlyContinue |
              Measure-Object Length -Sum).Sum
    return [math]::Round(($bytes / 1GB), 2)
}

function Remove-IfExists($path, $label) {
    if (-not (Test-Path $path)) {
        Write-Done "$label - 없음 (건너뜀)"
        return
    }
    try {
        Remove-Item $path -Recurse -Force -ErrorAction Stop
        Write-Done "$label - 지웠습니다"
    } catch {
        # 지우기 실패는 대개 그 파일을 잡고 있는 프로세스가 있다는 뜻이다.
        # 조용히 넘어가면 "지웠다"고 믿고 테스트해서 결과를 잘못 읽게 된다.
        Write-Host "   $label - 실패: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "     (앱이나 Ollama가 아직 떠 있을 수 있습니다)" -ForegroundColor Red
    }
}

# 이 앱의 사용자 데이터가 있을 수 있는 곳들.
#   - Electron의 userData: package.json의 name을 쓴다 (productName이 없으므로)
#   - config.py의 기본값: LOCAL_FILE_AI_HOME이 없을 때 (server.exe 단독 실행)
# 어느 쪽이 쓰이는지는 실행 형태에 따라 다르므로 있는 것을 전부 정리한다.
$appDataPaths = @(
    (Join-Path $env:APPDATA      'local-file-ai-app'),
    (Join-Path $env:APPDATA      'LocalFileAI'),
    (Join-Path $env:LOCALAPPDATA 'LocalFileAI')
)

$ollamaHome      = Join-Path $env:USERPROFILE '.ollama'
$ollamaModels    = Join-Path $ollamaHome 'models'
$ollamaProgram   = Join-Path $env:LOCALAPPDATA 'Programs\Ollama'
$ollamaLogs      = Join-Path $env:LOCALAPPDATA 'Ollama'
$appProgram      = Join-Path $env:LOCALAPPDATA 'Programs\LocalFileAI'

# ---------------------------------------------------------------- 지울 목록 미리 보기
Write-Step "지울 것"

$plan = @()
if ($Scope -in @('models', 'all')) {
    $size = Get-FolderSizeGb $ollamaModels
    $plan += "AI 모델 파일  $ollamaModels  (약 ${size}GB)"
}
if ($Scope -in @('app', 'all')) {
    foreach ($p in $appDataPaths) {
        if (Test-Path $p) { $plan += "앱 데이터     $p  (색인·설정·이력)" }
    }
    if ($plan.Count -eq 0) { $plan += "앱 데이터     (없음 — 아직 실행한 적이 없습니다)" }
}
if ($Scope -eq 'all') {
    $plan += "Ollama 제거   $ollamaProgram"
    $plan += "Ollama 설정   $ollamaHome (모델·키 전부)"
    $plan += "Ollama 로그   $ollamaLogs"
    if ($RemoveApp) { $plan += "LocalFileAI   $appProgram (앱 제거)" }
}
$plan | ForEach-Object { Write-Host "   - $_" }

if ($Scope -in @('models', 'all')) {
    Write-Host "`n   ⚠️  이 PC의 Ollama 모델이 전부 사라집니다." -ForegroundColor Yellow
    Write-Host "      다른 프로젝트에서 받아 둔 것이 있다면 그것도 함께 지워집니다." -ForegroundColor Yellow
    Write-Host "      먼저 확인: ollama list" -ForegroundColor Yellow
}

if (-not $Yes) {
    $answer = Read-Host "`n계속할까요? (yes 를 입력하면 진행)"
    if ($answer -ne 'yes') { Write-Host '취소했습니다.'; exit 0 }
}

# ---------------------------------------------------------------- 프로세스 정리
# 파일을 잡고 있으면 삭제가 실패한다. 지우기 전에 반드시 내려야 한다.
Write-Step "실행 중인 프로세스 정리"
foreach ($name in @('LocalFileAI', 'server', 'ollama app', 'ollama', 'llama-server')) {
    $found = Get-Process -Name $name -ErrorAction SilentlyContinue
    if ($found) {
        $found | Stop-Process -Force -ErrorAction SilentlyContinue
        Write-Done "$name - 종료했습니다"
    }
}
Start-Sleep -Seconds 2   # 핸들이 실제로 풀릴 시간

# ---------------------------------------------------------------- 실제 삭제
if ($Scope -in @('app', 'all')) {
    Write-Step "앱 데이터 삭제 (색인·설정·적용 이력)"
    foreach ($p in $appDataPaths) { Remove-IfExists $p "앱 데이터 $p" }
}

if ($Scope -eq 'models') {
    Write-Step "AI 모델 삭제"
    Remove-IfExists $ollamaModels '모델 파일'
}

if ($Scope -eq 'all') {
    Write-Step "Ollama 제거"

    # Inno Setup 설치본이면 조용히 제거할 수 있다. 없으면 폴더만 지운다.
    $uninstaller = Join-Path $ollamaProgram 'unins000.exe'
    if (Test-Path $uninstaller) {
        Write-Done '제거 프로그램 실행 중… (창이 안 뜹니다)'
        Start-Process $uninstaller -ArgumentList '/VERYSILENT', '/NORESTART' -Wait
        Write-Done '제거 완료'
    } else {
        Write-Done '제거 프로그램이 없습니다 — 폴더를 직접 지웁니다'
    }
    Remove-IfExists $ollamaProgram 'Ollama 프로그램 폴더'
    Remove-IfExists $ollamaHome    'Ollama 설정·모델 폴더'
    Remove-IfExists $ollamaLogs    'Ollama 로그 폴더'

    # 앱이 무설치본으로 깔아 둔 Ollama도 정리한다 (앱 데이터 삭제에 포함되지만,
    # 앱 데이터를 안 지우는 경로로 왔을 때를 대비해 한 번 더 확인한다).
    foreach ($p in $appDataPaths) {
        Remove-IfExists (Join-Path $p 'ollama-portable') '무설치 Ollama'
    }

    if ($RemoveApp) {
        Write-Step 'LocalFileAI 앱 제거'
        $appUninstaller = Get-ChildItem $appProgram -Filter 'Uninstall*.exe' `
                          -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($appUninstaller) {
            Start-Process $appUninstaller.FullName -ArgumentList '/S' -Wait
            Write-Done '제거 완료'
        } else {
            Write-Done '제거 프로그램을 못 찾았습니다 — 설정 > 앱에서 지워 주세요'
        }
        Remove-IfExists $appProgram 'LocalFileAI 프로그램 폴더'
    }
}

# ---------------------------------------------------------------- 결과 확인
Write-Step '남은 것 확인'

$ollamaResponds = $false
try {
    Invoke-WebRequest 'http://localhost:11434/api/tags' -TimeoutSec 3 -UseBasicParsing | Out-Null
    $ollamaResponds = $true
} catch { }

Write-Host "   Ollama 응답        : $(if ($ollamaResponds) { '예 (아직 떠 있습니다)' } else { '아니오' })"
Write-Host "   Ollama 설치 폴더   : $(if (Test-Path $ollamaProgram) { '있음' } else { '없음' })"
Write-Host "   모델 폴더          : $(if (Test-Path $ollamaModels) { "있음 ($(Get-FolderSizeGb $ollamaModels)GB)" } else { '없음' })"
foreach ($p in $appDataPaths) {
    if (Test-Path $p) { Write-Host "   앱 데이터 남음     : $p" -ForegroundColor Yellow }
}

if ($Scope -eq 'all' -and $ollamaResponds) {
    Write-Host "`n   ⚠️  Ollama가 아직 응답합니다. 제거가 끝나기 전에 확인했거나," -ForegroundColor Yellow
    Write-Host "      다른 프로그램이 11434 포트를 쓰고 있습니다." -ForegroundColor Yellow
    Write-Host "      확인: netstat -ano | findstr :11434" -ForegroundColor Yellow
}

Write-Host "`n끝났습니다. 이제 Setup.exe를 실행해 첫 설치 흐름을 확인하세요." -ForegroundColor Green
