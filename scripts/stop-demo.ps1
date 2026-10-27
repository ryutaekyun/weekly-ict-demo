# 로컬 시연 종료 - 포트 8000(FastAPI), 3000(Next.js)을 쓰는 프로세스를 정리한다.
foreach ($port in 8000, 3000) {
  $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  foreach ($c in $conns) {
    try { Stop-Process -Id $c.OwningProcess -Force -ErrorAction Stop; Write-Host "포트 $port 프로세스(PID $($c.OwningProcess))를 종료했습니다." -ForegroundColor Green } catch { Write-Host "포트 $port 프로세스를 종료하지 못했습니다: $($_.Exception.Message)" -ForegroundColor Yellow }
  }
  if (-not $conns) { Write-Host "포트 $port 는 이미 비어 있습니다." }
}
