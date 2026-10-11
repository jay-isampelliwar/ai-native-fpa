"""The auth routes: sign up, sign in, sign out, and who is signed in."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.core.config import get_settings
from app.db.session import get_session
from app.features.auth.exceptions import EmailTaken, InvalidCredentials
from app.features.auth.repository import UserRepository
from app.features.auth.schemas import SignInRequest, SignUpRequest, UserOut
from app.features.auth.security import SESSION_COOKIE, create_token
from app.features.auth.service import AuthService


router = APIRouter(prefix="/auth", tags=["auth"])


def set_session_cookie(response: Response, user_id: int) -> None:

    """Put a fresh signed token in an httpOnly cookie that page scripts cannot read."""

    settings = get_settings()

    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_token(user_id),
        max_age=settings.TOKEN_TTL_MINUTES * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
        )


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def sign_up(
    body: SignUpRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
    ) -> UserOut:

    """Create an account and sign the new user in straight away."""

    try:
        user = await AuthService(session).sign_up(body)

    except EmailTaken as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists") from exc

    set_session_cookie(response, user.id)

    return UserOut.from_user(user)


@router.post("/signin")
async def sign_in(
    body: SignInRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
    ) -> UserOut:

    """Check the email and password, then set the session cookie."""

    try:
        user = await AuthService(session).sign_in(body)

    except InvalidCredentials as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password") from exc

    set_session_cookie(response, user.id)

    return UserOut.from_user(user)


@router.post("/signout", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(response: Response) -> None:

    """Remove the session cookie, which ends the session in this browser."""

    response.delete_cookie(key=SESSION_COOKIE, path="/")


@router.get("/me")
async def me(
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
    ) -> UserOut:

    """Return the signed-in user, or 401 when the account behind the token is gone."""

    user = await UserRepository(session).get_by_id(user_id)

    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")

    return UserOut.from_user(user)
