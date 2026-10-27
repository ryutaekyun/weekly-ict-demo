"""수집 예약 작업자 — 웹사이트를 열지 않아도 정보원별 수집 주기에 따라 자료를 수집한다.

  python -m app.worker            # 계속 실행(기본 60초마다 점검)
  python -m app.worker --once     # 한 번만 점검·실행하고 종료(Windows 작업 스케줄러·cron 용)
  python -m app.worker --interval 30

예약 정보는 DB(sources.interval_minutes, collection_jobs)에 있어 서버·작업자를 재시작해도 유지되고, 같은 정보원의 중복 실행은 DB 규칙으로 막힌다.
실행 결과는 collection_jobs(trigger=schedule)와 로그 파일(storage/logs/worker.log)에 남는다.
"""
import argparse
import logging
import signal
import sys
import time
from pathlib import Path

from app.core.db import SessionLocal
from app.services.collection_jobs import schedule_tick

log = logging.getLogger("collector.worker")
_stop = False


def _setup_logging() -> None:
    Path("storage/logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("storage/logs/worker.log", encoding="utf-8")])


def _handle(*_) -> None:
    global _stop
    _stop = True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--source", action="append", help="이 정보원 ID만 점검(테스트·수동 확인용, 여러 번 지정 가능)")
    args = ap.parse_args()
    _setup_logging()
    signal.signal(signal.SIGINT, _handle)
    try:
        signal.signal(signal.SIGTERM, _handle)
    except (AttributeError, ValueError):
        pass
    log.info("수집 작업자 시작 (once=%s, interval=%ss)", args.once, args.interval)
    while not _stop:
        try:
            result = schedule_tick(SessionLocal, set(args.source) if args.source else None)
            log.info("점검 완료: 등록 %s건, 실행 %s건, 복구 %s건", result["enqueued"], len(result["ran"]), result["recovered"])
        except Exception as exc:  # noqa: BLE001 - 작업자는 오류로 죽지 않고 다음 주기에 다시 시도한다
            log.exception("점검 실패: %s", exc)
        if args.once:
            break
        for _ in range(args.interval):
            if _stop:
                break
            time.sleep(1)
    log.info("수집 작업자 종료")


if __name__ == "__main__":
    main()
