# 수집 작업자 시작 - 정보원별 주기에 따라 자료를 자동 수집한다(웹사이트를 열지 않아도 동작).
$root = Split-Path -Parent $PSScriptRoot
$api = Join-Path $root "apps\api"
$py = Join-Path $api ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "가상환경이 없습니다. apps\api 에서 python -m venv .venv 후 패키지를 설치하세요." -ForegroundColor Red; exit 1 }
Set-Location $api
$env:PYTHONUTF8 = "1"; $env:PYTHONPATH = "."
& $py -m app.worker
