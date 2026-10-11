from typing import List, Literal

from pydantic import BaseModel, Field, field_validator

from backend.app.core.users import EMAIL_RE


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_RE.match(value):
            raise ValueError("must be a valid email address")
        return value


class UserOut(BaseModel):
    email: str
    name: str
    role: Literal["admin", "hcp", "analyst"]
    role_title: str
    department: str
    allowed_routes: List[str]
    default_route: str
    must_change_password: bool = False


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)
