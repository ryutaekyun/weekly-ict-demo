"""원문 링크 품질 분류와 실제 접속 점검.

- classify_url: 네트워크 없이 URL 형태만 본다(없음·형식 오류·기관 홈페이지만·검색 결과 화면·개별 문서).
- check_link: 실제로 접속해 본다. '삭제·잘못된 주소(404/410)'와 '접속 제한(401/403/429·네트워크 차단)'을 구분해 기록한다.
  접속이 안 되는 것만으로 URL이 잘못되었다고 단정하지 않는다.
"""

import re
from urllib.parse import urlparse

import httpx

# 개별 문서 주소가 아니라 기관 첫 화면·검색 화면으로 보이는 경우를 찾는 보수적 규칙
SEARCH_PATH = re.compile(r"/(search|results?|find|query)(/|$)", re.IGNORECASE)


def classify_url(url: str | None) -> dict:
    """state: document / homepage / search / invalid / missing. blocked=True면 화면에서 원문 열기를 막고 사유를 보여준다."""
    if url is None or not url.strip():
        return {"state": "missing", "blocked": True, "is_pdf": False, "note": "원문 URL이 수집되지 않았습니다 — 출처 기관 사이트에서 직접 확인이 필요합니다"}
    raw = url.strip()
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or " " in raw:
        return {"state": "invalid", "blocked": True, "is_pdf": False, "note": "올바른 웹 주소(http/https)가 아니어서 열 수 없습니다"}
    path = parsed.path.rstrip("/")
    is_pdf = path.lower().endswith(".pdf")
    if path == "" and not parsed.query:
        return {"state": "homepage", "blocked": False, "is_pdf": False, "note": "기관 홈페이지 주소로 보입니다 — 개별 문서 주소인지 확인이 필요합니다"}
    if SEARCH_PATH.search(parsed.path) or re.search(r"(^|&)(q|query|keyword|search)=", parsed.query, re.IGNORECASE):
        return {"state": "search", "blocked": False, "is_pdf": False, "note": "검색 결과 화면 주소로 보입니다 — 개별 문서 주소인지 확인이 필요합니다"}
    return {"state": "document", "blocked": False, "is_pdf": is_pdf, "note": None}


def check_link(url: str, timeout: float = 12.0) -> dict:
    """실제 접속 점검. state: reachable / not_found / restricted / server_error / unreachable."""
    info = classify_url(url)
    if info["blocked"]:
        return {"state": info["state"], "http_status": None, "final_url": None, "note": info["note"]}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TNP-LinkCheck/1.0; +internal)"}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.head(url)
            if resp.status_code in (400, 403, 405, 501):  # 일부 서버는 HEAD를 막으므로 GET으로 한 번 더 확인
                resp = client.get(url)
        code = resp.status_code
        final = str(resp.url)
    except httpx.TimeoutException:
        return {"state": "unreachable", "http_status": None, "final_url": None, "note": "시간 초과 — 네트워크 또는 서버 접속 제한일 수 있어 주소가 잘못되었다고 단정할 수 없습니다"}
    except httpx.HTTPError as exc:
        return {"state": "unreachable", "http_status": None, "final_url": None, "note": f"접속하지 못했습니다({type(exc).__name__}) — 네트워크 제한일 수 있어 주소 오류로 단정할 수 없습니다"}
    if 200 <= code < 400:
        return {"state": "reachable", "http_status": code, "final_url": final, "note": None}
    if code in (404, 410):
        return {"state": "not_found", "http_status": code, "final_url": final, "note": "문서를 찾을 수 없습니다(삭제되었거나 주소가 잘못되었을 수 있음)"}
    if code in (401, 403, 429):
        return {"state": "restricted", "http_status": code, "final_url": final, "note": "서버가 접속을 제한했습니다(로그인·접속 제한) — 주소 오류와 구분해 기록합니다"}
    return {"state": "server_error", "http_status": code, "final_url": final, "note": f"서버 응답 오류({code})"}
