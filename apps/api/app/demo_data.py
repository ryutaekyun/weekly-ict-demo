"""시연 데이터 백업·복원 — 로컬 개발 DB(dev.db)만 대상으로 한다.

  python -m app.demo_data backup [--label 이름]    현재 DB를 backups/ 에 안전하게 복사(SQLite 온라인 백업)
  python -m app.demo_data list                      백업 목록
  python -m app.demo_data restore <파일명> --yes    선택한 백업으로 되돌림 — 되돌리기 전에 현재 DB를 먼저 자동 백업한다
  python -m app.demo_data stats                     자료·이슈·후보·원고 건수(시연 전후 비교용)

복원은 DB 파일을 바꾸므로 API 서버(uvicorn)를 먼저 멈춘 뒤 실행한다. 운영 DB·PostgreSQL에는 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB = Path("dev.db")
BACKUP_DIR = Path("../../backups")
TABLES = ["source_documents", "document_classifications", "issue_clusters", "candidates", "manuscripts", "reports", "report_exports", "card_news", "card_news_exports"]


def _db_path() -> Path:
    if not DB.exists():
        sys.exit(f"로컬 개발 DB({DB.resolve()})를 찾을 수 없습니다 — apps/api 폴더에서 실행하세요.")
    return DB


def backup(label: str = "") -> Path:
    src = _db_path()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    name = f"dev-{datetime.now():%Y%m%d-%H%M%S}{'-' + label if label else ''}.db"
    dest = BACKUP_DIR / name
    with sqlite3.connect(src) as s, sqlite3.connect(dest) as d:
        s.backup(d)
    print(f"백업 완료: {dest.resolve()} ({dest.stat().st_size // 1024}KB)")
    return dest


def listing() -> list[Path]:
    files = sorted(BACKUP_DIR.glob("dev-*.db")) if BACKUP_DIR.exists() else []
    for f in files:
        print(f"{f.name}  {f.stat().st_size // 1024}KB")
    if not files:
        print("백업이 없습니다.")
    return files


def restore(name: str, confirmed: bool) -> None:
    src = BACKUP_DIR / name
    if not src.exists():
        sys.exit(f"백업 파일이 없습니다: {src}")
    if not confirmed:
        sys.exit("복원하면 현재 DB가 바뀝니다. 확인했다면 --yes 를 붙여 다시 실행하세요(현재 DB는 먼저 자동 백업됩니다).")
    backup("before-restore")
    shutil.copyfile(src, _db_path())
    print(f"복원 완료: {name}")


def stats() -> dict:
    con = sqlite3.connect(_db_path())
    out = {}
    for t in TABLES:
        try:
            out[t] = con.execute(f"select count(*) from {t}").fetchone()[0]
        except sqlite3.Error:
            out[t] = None
    con.close()
    for k, v in out.items():
        print(f"{k}: {v}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup"); b.add_argument("--label", default="")
    sub.add_parser("list"); sub.add_parser("stats")
    r = sub.add_parser("restore"); r.add_argument("name"); r.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    if a.cmd == "backup":
        backup(a.label)
    elif a.cmd == "list":
        listing()
    elif a.cmd == "stats":
        stats()
    else:
        restore(a.name, a.yes)


if __name__ == "__main__":
    main()
