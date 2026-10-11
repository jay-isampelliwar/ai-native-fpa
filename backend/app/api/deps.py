"""Shared route dependencies, such as who is calling."""

from fastapi import Cookie, HTTPException, status

from app.features.auth.security import SESSION_COOKIE, read_token


def get_current_user_id(token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> int:

    """Return the calling user's id from the session cookie, or answer 401 when it is missing or invalid."""

    user_id = read_token(token) if token else None

    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")

    return user_id
