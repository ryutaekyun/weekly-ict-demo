from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # production 이면 안전하지 않은 설정(기본 비밀키·Secure 쿠키 꺼짐)으로는 서버가 시작되지 않는다
    app_env: str = "development"

    database_url: str = "sqlite:///./dev.db"
    jwt_secret: str = "change-me-in-env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12
    cors_origins: list[str] = ["http://localhost:3000"]

    # true(운영/HTTPS)로 설정하면 쿠키에 Secure 속성이 붙어 HTTPS에서만 전송된다.
    # 로컬 http 개발 환경에서는 false로 둬야 쿠키가 브라우저에 저장된다.
    cookie_secure: bool = False

    # 생성된 DOCX/PDF 출력본 저장 위치(서버 로컬, 공개 저장소에 올라가지 않음 — 인증된 API로만 내려받는다)
    export_dir: str = "./storage/exports"

    # 주간기술동향지 외부 저자 원고·첨부 파일 저장 위치(서버 로컬, 공개 저장소에 올라가지 않음)
    journal_dir: str = "./storage/journal"

    # 수집기 안전 설정: 사설·내부망 주소 수집은 기본 금지. 자동 테스트용 로컬 서버에서만 true 로 켠다(운영에서는 켤 수 없음)
    collector_allow_private_hosts: bool = False
    collector_max_response_bytes: int = 8 * 1024 * 1024
    collector_job_timeout_seconds: int = 600
    collector_stale_job_seconds: int = 180

    max_failed_login_attempts: int = 5
    login_lockout_minutes: int = 15

    @model_validator(mode="after")
    def _production_safety(self):
        if self.app_env == "production":
            if self.jwt_secret == "change-me-in-env" or len(self.jwt_secret) < 32:
                raise ValueError("운영 환경에서는 JWT_SECRET을 32자 이상의 무작위 값으로 설정해야 합니다")
            if self.collector_allow_private_hosts:
                raise ValueError("운영 환경에서는 COLLECTOR_ALLOW_PRIVATE_HOSTS 를 켤 수 없습니다")
            if not self.cookie_secure:
                raise ValueError("운영 환경에서는 COOKIE_SECURE=true(HTTPS)여야 합니다")
        return self


settings = Settings()
