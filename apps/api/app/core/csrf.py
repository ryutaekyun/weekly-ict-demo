"""더블 서브밋 쿠키 방식 CSRF 방어.

쿠키 기반 인증(브라우저)에만 적용된다 — Authorization 헤더로 인증하는 요청(테스트,
외부 API 클라이언트)은 애초에 브라우저가 자동으로 실어 보내지 않으므로 CSRF 공격
대상이 아니라서 검사를 건너뛴다.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.security import ACCESS_TOKEN_COOKIE, CSRF_COOKIE, CSRF_HEADER

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
EXEMPT_PATHS = {"/auth/login", "/auth/logout"}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in UNSAFE_METHODS and request.url.path not in EXEMPT_PATHS:
            has_bearer = request.headers.get("authorization", "").lower().startswith("bearer ")
            session_cookie = request.cookies.get(ACCESS_TOKEN_COOKIE)

            if not has_bearer and session_cookie:
                csrf_cookie = request.cookies.get(CSRF_COOKIE)
                csrf_header = request.headers.get(CSRF_HEADER)
                if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "CSRF 토큰이 유효하지 않습니다"},
                    )

        return await call_next(request)
