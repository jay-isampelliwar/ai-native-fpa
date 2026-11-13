"""Saving uploaded files under the upload folder and reading them back, one folder per user."""

import asyncio
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings


def upload_root() -> Path:

    """The folder every uploaded file lives under."""

    return Path(get_settings().UPLOAD_DIR)


async def save_file(
    user_id: int,
    ending: str,
    data: bytes
    ) -> str:

    """Write the file under the user's folder with a random name, and return its path relative to the upload folder."""

    relative = Path(str(user_id)) / f"{uuid4().hex}{ending}"
    target = upload_root() / relative

    await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(target.write_bytes, data)

    return relative.as_posix()


async def load_file(relative: str) -> bytes:

    """Read a saved file back by its relative path."""

    return await asyncio.to_thread((upload_root() / relative).read_bytes)
