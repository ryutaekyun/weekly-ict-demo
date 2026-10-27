"""수집 요청 안전장치 — 관리자가 입력한 정보원 주소로 서버가 요청을 보내므로 SSRF·과다 요청·대용량 응답을 막는다.

- http/https 만 허용(포트는 80·443·8080·8443 외 금지), 주소에 계정정보(user:pass@) 금지
- DNS를 직접 풀어 내부망·루프백·링크로컬·예약 주소로 향하면 차단(리디렉션 때마다 다시 검사 — httpx request 훅)
- 응답 크기 상한(Content-Length 선검사 + 수신 후 검사), 연결·읽기 시간 제한
- 같은 호스트에는 정보원별 최소 간격을 지켜 요청(arXiv 등 공식 호출 빈도 안내 준수)
- robots.txt 존중(정보원 설정 respect_robots) — 거부되면 우회하지 않고 사유를 기록
※ DNS 확인과 실제 연결 사이의 재바인딩 공격은 완전히 막지 못한다(관리자 전용 기능이라는 점과 함께 문서에 한계로 기재).
"""
from __future__ import annotations

import ipaddress
import socket
import threading
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.core.config import settings

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {None, 80, 443, 8080, 8443}


class UnsafeURLError(Exception):
    """안전 규칙에 막힌 주소 — 수집 오류 유형 'blocked_url' 로 기록된다."""


class ResponseTooLargeError(Exception):
    pass


class RobotsDisallowedError(Exception):
    pass


def _is_public_ip(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


def assert_safe_url(url: str, *, resolve: bool = True) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f"허용되지 않는 프로토콜입니다: {parsed.scheme or '(없음)'} — http/https 만 사용할 수 있습니다")
    if not parsed.hostname:
        raise UnsafeURLError("주소에 호스트가 없습니다")
    if parsed.username or parsed.password:
        raise UnsafeURLError("주소에 계정정보를 넣을 수 없습니다")
    if settings.collector_allow_private_hosts:
        return  # 자동 테스트용 로컬 서버 전용(운영에서는 설정 자체가 거부됨)
    if parsed.port not in ALLOWED_PORTS:
        raise UnsafeURLError(f"허용되지 않는 포트입니다: {parsed.port}")
    if not resolve:
        return  # 등록 시에는 형식만 검사하고, 실제 접속할 때마다 DNS를 풀어 내부망 여부를 다시 검사한다
    host = parsed.hostname
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"호스트를 찾을 수 없습니다: {host}") from exc
    for info in infos:
        ip = info[4][0]
        if not _is_public_ip(ip):
            raise UnsafeURLError(f"내부망·예약 주소({ip})로 향하는 주소는 수집할 수 없습니다")


# ------------------------------------------------------------ 호스트별 요청 간격 ----
_last_request: dict[str, float] = {}
_throttle_lock = threading.Lock()
_throttle_seconds: dict[str, float] = {}


def set_host_interval(host: str, seconds: float) -> None:
    _throttle_seconds[host] = max(0.0, min(seconds, 30.0))


def _throttle(host: str) -> None:
    interval = _throttle_seconds.get(host, 0.0)
    if interval <= 0:
        return
    with _throttle_lock:
        wait = _last_request.get(host, 0.0) + interval - time.monotonic()
        if wait > 0:
            time.sleep(min(wait, 30.0))
        _last_request[host] = time.monotonic()


def _on_request(request: httpx.Request) -> None:
    assert_safe_url(str(request.url))  # 리디렉션으로 새 주소가 올 때마다 다시 호출된다
    _throttle(request.url.host)


def _on_response(response: httpx.Response) -> None:
    length = response.headers.get("content-length")
    if length and length.isdigit() and int(length) > settings.collector_max_response_bytes:
        raise ResponseTooLargeError(f"응답이 너무 큽니다({int(length) // 1024}KB > {settings.collector_max_response_bytes // 1024}KB)")


def guarded_client(user_agent: str, timeout: float = 15.0) -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(timeout, connect=6.0),
        headers={"User-Agent": user_agent},
        follow_redirects=True,
        max_redirects=5,
        event_hooks={"request": [_on_request], "response": [_on_response]},
    )


def check_size(content: bytes) -> bytes:
    if len(content) > settings.collector_max_response_bytes:
        raise ResponseTooLargeError(f"응답이 너무 큽니다({len(content) // 1024}KB)")
    return content


# ------------------------------------------------------------------ robots.txt ----
_robots_cache: dict[str, tuple[float, RobotFileParser | None]] = {}


def robots_allowed(url: str, user_agent: str) -> bool:
    """robots.txt 가 해당 주소 수집을 허용하는지. robots.txt 를 못 가져오면(없음·오류) 허용으로 본다(표준 관행)."""
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    cached = _robots_cache.get(base)
    if cached is None or time.time() - cached[0] > 3600:
        rp: RobotFileParser | None = RobotFileParser()
        try:
            with guarded_client(user_agent, timeout=8.0) as client:
                resp = client.get(f"{base}/robots.txt")
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            else:
                rp = None
        except Exception:  # noqa: BLE001 - robots.txt 확인 실패가 수집 자체를 막지는 않는다
            rp = None
        _robots_cache[base] = (time.time(), rp)
        cached = _robots_cache[base]
    rp = cached[1]
    return True if rp is None else rp.can_fetch(user_agent, url)


def clear_robots_cache() -> None:
    _robots_cache.clear()
