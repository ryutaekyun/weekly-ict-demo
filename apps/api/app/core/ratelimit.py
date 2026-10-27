"""간단한 프로세스 내 요청 횟수 제한 — 가입 신청 남용 방지용. (다중 서버로 확장하면 공용 저장소(Redis 등)로 바꿔야 한다.)"""
import threading
import time
from collections import defaultdict, deque

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def allow(key: str, limit: int, window_seconds: int) -> bool:
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and q[0] < now - window_seconds:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def reset() -> None:
    with _lock:
        _hits.clear()
