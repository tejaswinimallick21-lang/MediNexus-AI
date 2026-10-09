from fastapi import APIRouter, Depends, Request, Response, status

from backend.app.core.config import settings
from backend.app.core.deps import current_user
from backend.app.core.errors import APIError
from backend.app.core.security import create_session_token, decode_session_token
from backend.app.core.users import UserRecord, get_user
from backend.app.schemas.auth import LoginIn, UserOut
from backend.app.schemas.common import ERROR_RESPONSES
from backend.app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"], responses=ERROR_RESPONSES)


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, response: Response) -> UserOut:
    user = auth_service.authenticate(body.email, body.password)
    if user is None:
        raise APIError(401, "invalid_credentials", "Invalid email or password.")
    response.set_cookie(
        key=settings.cookie_name,
        value=create_session_token(user.email),
        max_age=settings.jwt_ttl_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return auth_service.to_user_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> Response:
    token = request.cookies.get(settings.cookie_name)
    email = decode_session_token(token) if token else None
    user = get_user(email) if email else None
    if user:
        auth_service.record_logout(user)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(settings.cookie_name, path="/")
    return response


@router.get("/me", response_model=UserOut)
def me(user: UserRecord = Depends(current_user)) -> UserOut:
    return auth_service.to_user_out(user)
