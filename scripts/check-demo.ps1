# 로컬 시연 환경 점검 - FastAPI, Next.js, DB 연결 여부와 오류 원인/해결 방법을 표시한다.
param([switch]$Wait)
$root = Split-Path -Parent $PSScriptRoot
$api = Join-Path $root "apps\api"
$py = Join-Path $api ".venv\Scripts\python.exe"
$ok = $true

function Probe($url, $tries) {
  for ($i = 0; $i -lt $tries; $i++) {
    try { $r = Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 5; return $r.StatusCode } catch { Start-Sleep 2 }
  }
  return 0
}
$tries = if ($Wait) { 30 } else { 1 }

$h = Probe "http://localhost:8000/health" $tries
if ($h -eq 200) { Write-Host "[정상] FastAPI 연결 (http://localhost:8000/health)" -ForegroundColor Green }
else { $ok = $false; Write-Host "[오류] FastAPI에 연결할 수 없습니다" -ForegroundColor Red; Write-Host "  원인/해결: 서버가 시작되지 않았거나 포트 8000을 다른 프로그램이 쓰고 있습니다. scripts\stop-demo.ps1 후 start-demo.ps1 을 다시 실행하세요. 계속되면 apps\api 에서 '.venv\Scripts\python -m uvicorn app.main:app --port 8000' 로 오류 메시지를 확인하세요." -ForegroundColor Yellow }

$n = Probe "http://localhost:3000/login" $tries
if ($n -eq 200) { Write-Host "[정상] Next.js 연결 (http://localhost:3000)" -ForegroundColor Green }
else { $ok = $false; Write-Host "[오류] Next.js에 연결할 수 없습니다" -ForegroundColor Red; Write-Host "  원인/해결: 처음 시작은 1~2분 걸릴 수 있습니다. 계속 실패하면 apps\web 에서 'npm install' 후 'npm run dev' 를 직접 실행해 오류를 확인하세요." -ForegroundColor Yellow }

if (Test-Path $py) {
  Push-Location $api
  $env:PYTHONUTF8 = "1"; $env:PYTHONPATH = "."
  $out = & $py -c "from sqlalchemy import func, select; from app.core.db import SessionLocal; from app.models.source_document import SourceDocument; from app.models.user import User; db=SessionLocal(); print(db.scalar(select(func.count()).select_from(SourceDocument)), db.scalar(select(func.count()).select_from(User)))" 2>&1
  Pop-Location
  if ($LASTEXITCODE -eq 0 -and "$out" -match "^\d+ \d+$") { $p = "$out" -split " "; Write-Host "[정상] DB 연결 - 수집 문서 $($p[0])건, 사용자 계정 $($p[1])개" -ForegroundColor Green }
  else { $ok = $false; Write-Host "[오류] DB에 연결할 수 없습니다: $out" -ForegroundColor Red; Write-Host "  해결: apps\api 에서 '.venv\Scripts\python -m alembic upgrade head' 를 실행해 DB를 최신 상태로 만드세요." -ForegroundColor Yellow }
}

if ($ok) {
  Write-Host ""
  Write-Host "로컬 시연 환경이 정상입니다. 브라우저에서 http://localhost:3000 을 여세요." -ForegroundColor Green
  Write-Host "로그인: 시연용 가상 계정만 사용합니다. 계정이 없거나 비밀번호를 모르면 docs\DEMO_GUIDE.md 의 '시연 계정' 절을 따르세요(비밀번호는 저장소에 없고 실행할 때 무작위로 만들어집니다)." -ForegroundColor Cyan
  Write-Host "참고: 이 버전은 유료 AI를 사용하지 않습니다(키 설정 불필요). GitHub Pages 공개 시연은 읽기 전용입니다." -ForegroundColor Cyan
} else { exit 1 }
