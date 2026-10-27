# TNP AI Platform - 로컬 통합 시연 시작 (FastAPI 8000 + Next.js 3000)
# 사용: PowerShell에서 .\scripts\start-demo.ps1   (또는 scripts\start-demo.bat 더블클릭)
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$api = Join-Path $root "apps\api"
$web = Join-Path $root "apps\web"
$py = Join-Path $api ".venv\Scripts\python.exe"

function Fail($what, $fix) { Write-Host "[오류] $what" -ForegroundColor Red; Write-Host "  해결: $fix" -ForegroundColor Yellow; exit 1 }

# 1) 사전 점검
if (-not (Test-Path $py)) { Fail "백엔드 가상환경이 없습니다 ($py)" "apps\api 에서 'python -m venv .venv' 후 '.venv\Scripts\pip install -r requirements.txt' 를 실행하세요." }
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCmd) {
  $cand = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Filter "OpenJS.NodeJS*" -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($cand) { $nd = Get-ChildItem $cand.FullName -Directory -Filter "node-*" | Select-Object -First 1; if ($nd) { $env:PATH = "$($nd.FullName);$env:PATH" } }
  $nodeCmd = Get-Command node -ErrorAction SilentlyContinue
}
if (-not $nodeCmd) { Fail "Node.js를 찾지 못했습니다" "Node.js LTS를 설치(winget install OpenJS.NodeJS.LTS)한 뒤 새 PowerShell 창에서 다시 실행하세요." }
if (-not (Test-Path (Join-Path $web "node_modules"))) { Fail "프런트엔드 패키지가 설치되지 않았습니다" "apps\web 에서 'npm install' 을 실행하세요." }

# 2) 이 버전은 유료 AI를 코드 수준에서 차단하므로 키·환경변수 설정이 필요 없다
Remove-Item Env:AI_PROVIDER, Env:ANTHROPIC_API_KEY, Env:OPENAI_API_KEY -ErrorAction SilentlyContinue

# 3) DB 마이그레이션(이미 최신이면 변화 없음)
Push-Location $api
$env:PYTHONUTF8 = "1"; $env:PYTHONPATH = "."
& $py -m alembic upgrade head 2>&1 | Select-Object -Last 1
Pop-Location

# 4) 서버 시작(숨김 창) — 이미 떠 있으면 건너뜀
foreach ($port in 8000, 3000) {
  $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($c) { Write-Host "[안내] 포트 $port 는 이미 사용 중입니다(PID $($c.OwningProcess)) — 그대로 사용합니다. 새로 시작하려면 scripts\stop-demo.ps1 을 먼저 실행하세요." -ForegroundColor Yellow }
}
if (-not (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)) {
  Start-Process -FilePath $py -ArgumentList "-m", "uvicorn", "app.main:app", "--port", "8000" -WorkingDirectory $api -WindowStyle Hidden
}
if (-not (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)) {
  Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "npm run dev" -WorkingDirectory $web -WindowStyle Hidden
}

# 5) 연결 확인
& (Join-Path $PSScriptRoot "check-demo.ps1") -Wait
