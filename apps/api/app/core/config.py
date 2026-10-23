from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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

    max_failed_login_attempts: int = 5
    login_lockout_minutes: int = 15


settings = Settings()
