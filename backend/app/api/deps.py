"""Shared route dependencies, such as who is calling."""

from app.core.config import get_settings


def get_current_user_id() -> int:

    """Return the calling user's id, fixed to the dev user until login exists."""

    return get_settings().DEV_USER_ID
