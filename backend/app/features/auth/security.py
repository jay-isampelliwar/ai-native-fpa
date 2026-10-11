"""Password hashing and the signed session token that is kept in a cookie."""

from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings


SESSION_COOKIE = "mosaic_session"
TOKEN_ALGORITHM = "HS256"

password_hasher = PasswordHash.recommended()

DUMMY_HASH = password_hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:

    """Turn a plain password into an Argon2 hash that is safe to store."""

    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:

    """Check a password against its hash, spending the same time even when there is no hash."""

    if password_hash is None:

        password_hasher.verify(password, DUMMY_HASH)

        return False

    return password_hasher.verify(password, password_hash)


def create_token(user_id: int) -> str:

    """Sign a token that says which user this is and when it stops working."""

    settings = get_settings()

    expires_at = datetime.now(UTC) + timedelta(minutes=settings.TOKEN_TTL_MINUTES)

    payload = {"sub": str(user_id), "exp": expires_at}

    return jwt.encode(payload, settings.JWT_SECRET.get_secret_value(), algorithm=TOKEN_ALGORITHM)


def read_token(token: str) -> int | None:

    """Return the user id inside a valid token, or None when it is expired, changed or broken."""

    settings = get_settings()

    try:
        payload = jwt.decode(token, settings.JWT_SECRET.get_secret_value(), algorithms=[TOKEN_ALGORITHM])

    except jwt.PyJWTError:
        return None

    subject = payload.get("sub")

    if not isinstance(subject, str) or not subject.isdigit():
        return None

    return int(subject)
