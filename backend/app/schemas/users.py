"""Schemas for people management (Security & Infrastructure → People)."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from backend.app.core.users import EMAIL_RE

Role = Literal["admin", "hcp", "analyst"]


class UserAdminRow(BaseModel):
    email: str
    name: str
    role: Role
    role_title: str
    department: str
    active: bool
    must_change_password: bool
    created_at: Optional[str] = None
    created_by: str
    last_login_at: Optional[str] = None
    is_you: bool


class UserDirectory(BaseModel):
    users: List[UserAdminRow]
    active_count: int
    admin_count: int


class UserCreateIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    name: str = Field(min_length=1, max_length=80)
    role: Role
    department: str = Field("", max_length=80)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_RE.match(value):
            raise ValueError("must be a valid email address")
        return value

    @field_validator("name", "department")
    @classmethod
    def _trim(cls, value: str) -> str:
        return value.strip()


class UserUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    role: Optional[Role] = None
    department: Optional[str] = Field(None, max_length=80)
    active: Optional[bool] = None


class TemporaryPassword(BaseModel):
    """Shown once to the administrator; the person must replace it at first sign-in."""

    user: UserAdminRow
    temporary_password: str
