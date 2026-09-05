"""Where uploaded documents are kept, behind an interface that hides whether that is disk or a bucket.

Bank statements are among the most sensitive files a person owns. Keeping them behind a protocol
rather than scattering ``open()`` calls means the decisions that matter - where they live, who can
read them, when they are deleted - are made in one place and can be changed without touching the
extraction pipeline.

Files are stored under a key derived from the user and a random id, never from the filename. A
user supplied name is untrusted input, and one containing path separators would otherwise decide
where the file lands. The original name is kept in the database for display only.

Content is hashed on write and the checksum stored with the import. Uploading the same statement
twice is common - people forget - and comparing checksums turns that into a recognisable duplicate
rather than a second copy of every transaction.

Local disk is the Phase 3 implementation and is adequate for one machine. The protocol exists so
object storage replaces it without any caller changing; what must not happen is a second storage
path appearing beside this one.
"""

import hashlib
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from app.core.config import settings


class DocumentStorage(Protocol):

    """The interface the import pipeline depends on, independent of where bytes actually live."""

    async def put(self, user_id: int, content: bytes, suffix: str) -> tuple[str, str]: ...

    async def get(self, storage_key: str) -> bytes: ...

    async def delete(self, storage_key: str) -> None: ...


class LocalDocumentStorage:

    """Stores uploads on local disk under a per user directory, keyed by a random id."""

    def __init__(self, root: Path | None = None) -> None:

        """Take the directory uploads live under, creating it if this is a fresh environment."""

        self._root = root or Path(settings.upload_directory)

        self._root.mkdir(parents=True, exist_ok=True)

    async def put(self, user_id: int, content: bytes, suffix: str) -> tuple[str, str]:

        """Write one document under a generated key and return that key with its checksum."""

        checksum = hashlib.sha256(content).hexdigest()

        key = f"{user_id}/{uuid4().hex}{suffix}"

        path = self._root / key

        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_bytes(content)

        return key, checksum

    async def get(self, storage_key: str) -> bytes:

        """Read back one stored document by the key that was returned when it was written."""

        return (self._root / storage_key).read_bytes()

    async def delete(self, storage_key: str) -> None:

        """Remove one stored document, used when an import is abandoned rather than committed."""

        path = self._root / storage_key

        if path.exists():
            path.unlink()


document_storage: DocumentStorage = LocalDocumentStorage()
