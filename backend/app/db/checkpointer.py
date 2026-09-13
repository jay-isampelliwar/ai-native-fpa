
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
    ("app.agent.user_data", "UserProfile"),
    ("app.agent.user_data", "Income"),
    ("app.agent.user_data", "Expense"),
    ("app.agent.user_data", "Loan"),
    ("app.agent.user_data", "Emi"),
    ("app.agent.user_data", "Sip"),
    ("app.agent.user_data", "MutualFund"),
    ("app.agent.user_data", "Stock"),
    ("app.agent.user_data", "Deposit"),
    ("app.agent.user_data", "RetirementAsset"),
    ("app.agent.user_data", "InsurancePolicy"),
    ("app.agent.user_data", "Goal"),
    ("app.agent.user_data", "Spend"),
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
