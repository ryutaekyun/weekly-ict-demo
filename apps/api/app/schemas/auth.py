import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    role: UserRole
    job_title: str | None = None
    is_active: bool
    approval_status: str = "approved"
    favorite_fields: list[str] = []
    last_login_at: datetime | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


def _strong(pw: str) -> str:
    if not any(c.isalpha() for c in pw) or not any(c.isdigit() for c in pw):
        raise ValueError("비밀번호는 영문과 숫자를 모두 포함해야 합니다")
    return pw


class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=10, max_length=128)
    job_title: str | None = Field(default=None, max_length=100)
    invite_token: str | None = None

    @field_validator("password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return _strong(v)


class RegisterResponse(BaseModel):
    status: str  # pending | approved
    message: str


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=100)
    job_title: str | None = Field(default=None, max_length=100)
    favorite_fields: list[str] | None = None
