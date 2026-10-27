"""E2E 전용 API 서버 실행기 — 개발 DB(dev.db)를 건드리지 않고, 실행할 때마다 dev.db 복사본(e2e.db)으로 새로 시작한다.

Playwright(webServer)가 호출한다: apps/web 폴더 기준 `..\\api\\.venv\\Scripts\\python.exe ../../scripts/run_e2e_api.py`
- 테스트가 만든 데이터는 e2e.db에만 남고 다음 실행 때 버려진다 → 반복 실행해도 같은 출발 상태.
- 모의 AI 공급자(테스트 모드)·사설 주소 수집 허용(로컬 테스트 서버용)은 이 서버에서만 켠다. 실제 업무 서버에는 해당 설정이 없다.
"""
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps" / "api"
dev, e2e = API_DIR / "dev.db", API_DIR / "e2e.db"

for suffix in ("", "-wal", "-shm", "-journal"):
    f = Path(str(e2e) + suffix)
    if f.exists():
        f.unlink()
if dev.exists():
    with sqlite3.connect(dev) as s, sqlite3.connect(e2e) as d:
        s.backup(d)
    # 개발 DB에 남은 이전 AI 분석·검증 기록은 지운다(모의 결과뿐이며, 'AI 분석 선행 상태'에 테스트가 의존하지 않게 한다)
    with sqlite3.connect(e2e) as c:
        for tbl in ("ai_evaluations", "ai_claims", "ai_insertions", "ai_call_approvals", "ai_analyses"):
            try:
                c.execute(f"delete from {tbl}")
            except sqlite3.Error:
                pass
        c.commit()
env = {
    **os.environ,
    "DATABASE_URL": f"sqlite:///{e2e.as_posix()}",
    "CORS_ORIGINS": '["http://localhost:3100","http://localhost:3000"]',
    "AI_PROVIDER": "mock",
    "AI_ALLOW_MOCK": "1",
    "AI_MOCK_FLAWS": "1",
    "AI_DAILY_LIMIT": "500",
    "COLLECTOR_ALLOW_PRIVATE_HOSTS": "1",
    "PYTHONUTF8": "1",
    "PYTHONPATH": str(API_DIR),
}
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=API_DIR, env=env, check=True)
sys.exit(subprocess.call([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "localhost", "--port", "8010"], cwd=API_DIR, env=env))
