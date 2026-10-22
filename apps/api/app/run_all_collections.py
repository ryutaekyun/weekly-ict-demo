"""모든 활성 출처에 대해 1회 수집을 실행하는 1회성 스크립트 — Phase 2-2 개발·검증용 실데이터 확보.

실행: python -m app.run_all_collections
"""

from app.core.db import SessionLocal
from app.models.source import Source
from app.services.collection import run_collection


def main() -> None:
    db = SessionLocal()
    try:
        sources = db.query(Source).filter(Source.is_active.is_(True)).all()
        for source in sources:
            run = run_collection(db, source)
            print(
                f"[{source.field_code.value}] {source.name}: {run.status.value} "
                f"(found={run.items_found}, new={run.items_new}, dup={run.items_duplicate}, "
                f"updated={run.items_updated}, error={run.error_type})"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
