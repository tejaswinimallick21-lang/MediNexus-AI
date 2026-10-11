"""People management routes (/api/users/*), administrators only (Security & Infrastructure)."""

from fastapi import APIRouter, Depends, Path

from backend.app.core.deps import require_page
from backend.app.core.users import UserRecord
from backend.app.schemas.common import ERROR_RESPONSES
from backend.app.schemas.users import TemporaryPassword, UserAdminRow, UserCreateIn, UserDirectory, UserUpdateIn
from backend.app.services import users

router = APIRouter(prefix="/users", tags=["users"], responses=ERROR_RESPONSES)
admin = require_page("it")
Email = Path(..., min_length=3, max_length=254)


@router.get("", response_model=UserDirectory)
def directory(me: UserRecord = Depends(admin)) -> UserDirectory:
    return users.directory(me)


@router.post("", response_model=TemporaryPassword, status_code=201)
def create(body: UserCreateIn, me: UserRecord = Depends(admin)) -> TemporaryPassword:
    return users.create(body, me)


@router.patch("/{email}", response_model=UserAdminRow)
def update(body: UserUpdateIn, email: str = Email, me: UserRecord = Depends(admin)) -> UserAdminRow:
    return users.update(email, body, me)


@router.post("/{email}/reset-password", response_model=TemporaryPassword)
def reset_password(email: str = Email, me: UserRecord = Depends(admin)) -> TemporaryPassword:
    return users.reset_password(email, me)
