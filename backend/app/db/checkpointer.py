"""The production checkpointer, and the encryption layer that sits underneath it.

A LangGraph checkpoint is the paused state of a real user's request. For this product
that means a proposed SIP change, the surplus figures behind it and the record ids it
cites, sitting in a table until someone answers. It is the one place where working
financial state rests outside the application database, so it is encrypted at rest with a
key this service holds rather than relying on the database's own encryption alone.

``EncryptedSerializer`` wraps the serialiser LangGraph would otherwise use rather than
replacing it. The inner serialiser still decides how objects become bytes - which is what
keeps pydantic models, dates and Decimals round tripping correctly - and this class only
encrypts the bytes that come out. Swapping in a different inner serialiser later changes
nothing here.

AES-GCM is used rather than plain AES because it authenticates as well as encrypts. A
checkpoint that has been tampered with fails to decrypt instead of resuming as something
slightly different, which matters when the object being restored is a pending instruction
to move money. The nonce is generated per record and stored alongside the ciphertext.

Rotating ``checkpoint_encryption_key`` invalidates every stored checkpoint, because old
records cannot be decrypted with a new key. That is a migration - drain or expire pending
approvals first - not a redeploy, which is why the key is a required setting with no
default that could be silently regenerated.

``ALLOWED_CHECKPOINT_TYPES`` is the closed list of our own classes that may be rebuilt
from a checkpoint. Deserialisation reconstructs objects from stored bytes, so an open
allowlist means whatever a row names gets imported and instantiated. Listing the types
explicitly keeps that decision in this file, and a new type added to ``PlannerState``
must be added here too or it will be refused rather than silently trusted.
"""

import os
from contextlib import asynccontextmanager
from hashlib import sha256

from Crypto.Cipher import AES
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.base import SerializerProtocol
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.core.config import settings

ALLOWED_CHECKPOINT_TYPES = (
    ("app.core.security", "AuthenticatedUser"),
    ("app.agent.context", "AgentContext"),
    ("app.ui.blocks", "TextBlock"),
    ("app.ui.blocks", "KpiBlock"),
    ("app.ui.blocks", "TableBlock"),
    ("app.ui.blocks", "TableColumn"),
    ("app.ui.blocks", "ChartBlock"),
    ("app.ui.blocks", "ChartPoint"),
    ("app.ui.blocks", "ChartMarker"),
    ("app.ui.blocks", "CalloutBlock"),
    ("app.ui.blocks", "PromptBlock"),
    ("app.ui.blocks", "PromptItem"),
    ("app.ui.blocks", "ApprovalCardBlock"),
    ("app.ui.blocks", "FieldChange"),
)

NONCE_BYTES = 12
TAG_BYTES = 16
ENCRYPTED_TYPE = "aesgcm"


class EncryptedSerializer:

    """Wraps another serialiser and encrypts its output with AES-GCM before it reaches the database."""

    def __init__(
        self,
        key: str,
        inner: SerializerProtocol | None = None,
        ) -> None:

        """Derive a fixed length key from the configured secret and keep the serialiser being wrapped."""

        self._key = sha256(key.encode("utf-8")).digest()
        self._inner = inner or JsonPlusSerializer(allowed_msgpack_modules=ALLOWED_CHECKPOINT_TYPES)

    def dumps(self, obj: object) -> bytes:

        """Serialise and encrypt one object, used for the values LangGraph stores untyped."""

        return self._encrypt(self._inner.dumps(obj))

    def loads(self, data: bytes) -> object:

        """Decrypt and deserialise one value written by ``dumps``."""

        return self._inner.loads(self._decrypt(data))

    def dumps_typed(self, obj: object) -> tuple[str, bytes]:

        """Serialise with the inner type tag, then hide that tag inside the encrypted payload."""

        inner_type, payload = self._inner.dumps_typed(obj)

        header = inner_type.encode("utf-8")

        body = len(header).to_bytes(2, "big") + header + payload

        return ENCRYPTED_TYPE, self._encrypt(body)

    def loads_typed(self, data: tuple[str, bytes]) -> object:

        """Recover the inner type tag from the decrypted payload and hand both to the inner serialiser."""

        type_name, payload = data

        if type_name != ENCRYPTED_TYPE:
            return self._inner.loads_typed(data)

        body = self._decrypt(payload)

        header_length = int.from_bytes(body[:2], "big")

        inner_type = body[2 : 2 + header_length].decode("utf-8")

        return self._inner.loads_typed((inner_type, body[2 + header_length :]))

    def _encrypt(self, payload: bytes) -> bytes:

        """Encrypt one payload under a fresh nonce, returning nonce, tag and ciphertext as one blob."""

        nonce = os.urandom(NONCE_BYTES)

        cipher = AES.new(self._key, AES.MODE_GCM, nonce=nonce)

        ciphertext, tag = cipher.encrypt_and_digest(payload)

        return nonce + tag + ciphertext

    def _decrypt(self, blob: bytes) -> bytes:

        """Verify and decrypt one blob, failing loudly if it was altered or written under another key."""

        nonce = blob[:NONCE_BYTES]

        tag = blob[NONCE_BYTES : NONCE_BYTES + TAG_BYTES]

        cipher = AES.new(self._key, AES.MODE_GCM, nonce=nonce)

        return cipher.decrypt_and_verify(blob[NONCE_BYTES + TAG_BYTES :], tag)


@asynccontextmanager
async def postgres_checkpointer():

    """Open the encrypted PostgreSQL checkpointer for the life of the application."""

    serde = EncryptedSerializer(settings.checkpoint_encryption_key.get_secret_value())

    async with AsyncPostgresSaver.from_conn_string(
        settings.database_url.get_secret_value(),
        serde=serde,
    ) as saver:

        yield saver


async def run_checkpoint_migrations() -> None:

    """Create or upgrade the checkpoint tables, run as a deliberate deployment step."""

    async with postgres_checkpointer() as saver:

        await saver.setup()
