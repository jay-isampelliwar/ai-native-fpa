"""Checks that a paused approval is unreadable and unforgeable while it waits in the database.

A checkpoint holds a proposed change to someone's money between the moment it is
described and the moment they answer. These tests assert two properties of that gap:
nobody reading the table can see what was proposed, and nobody writing to the table can
change it.

The plaintext assertion searches the stored bytes for values that were definitely in the
object. That is a blunt check and it is meant to be - it fails if encryption is
accidentally disabled, if a future serialiser writes a readable envelope around the
payload, or if a field is stored outside the encrypted body.

The tamper test flips a single byte of ciphertext and requires a failure. AES-GCM is used
precisely so that a modified checkpoint refuses to load rather than resuming as something
slightly different, which is the difference between a failed request and an instruction
the user never approved.

These run without PostgreSQL. The serialiser is the part that must hold, and testing it
directly keeps the guarantee covered in environments where a database is not available.
"""

from decimal import Decimal

import pytest

from app.db.checkpointer import ENCRYPTED_TYPE, EncryptedSerializer
from app.ui.blocks import KpiBlock

PENDING_CHANGE = {
    "skill": "sip_modification",
    "from_amount": Decimal("10000.00"),
    "to_amount": Decimal("15000.00"),
    "evidence_ids": ["sip_1", "inc_1"],
    "scheme": "Parag Parikh Flexi Cap",
}


@pytest.fixture
def serializer():

    """A serialiser under a known test key, so tampering and key mismatch can both be exercised."""

    return EncryptedSerializer("test-key")


def test_stored_payload_is_typed_as_encrypted(serializer):

    """The type tag written to the database names the encryption, never the inner python type."""

    type_name, _ = serializer.dumps_typed(PENDING_CHANGE)

    assert type_name == ENCRYPTED_TYPE


def test_no_field_of_a_pending_change_is_readable_at_rest(serializer):

    """Amounts, record ids and scheme names are all absent from the bytes stored in the table."""

    _, blob = serializer.dumps_typed(PENDING_CHANGE)

    for secret in (b"15000", b"10000", b"sip_1", b"Parag Parikh", b"sip_modification"):
        assert secret not in blob


def test_round_trip_restores_types_exactly(serializer):

    """A decimal comes back as a decimal, so a resumed approval proposes the same amount to the paisa."""

    restored = serializer.loads_typed(serializer.dumps_typed(PENDING_CHANGE))

    assert restored == PENDING_CHANGE
    assert isinstance(restored["to_amount"], Decimal)


def test_pydantic_blocks_survive_the_round_trip(serializer):

    """A block stored in checkpointed state comes back as a block, with its Decimal still a Decimal."""

    block = KpiBlock(
        label="Free surplus",
        display="INR 70,000",
        value=Decimal("70000.00"),
        evidence_ids=["inc_1"],
    )

    restored = serializer.loads_typed(serializer.dumps_typed(block))

    assert restored.evidence_ids == ["inc_1"]
    assert isinstance(restored.value, Decimal)
    assert restored.value == Decimal("70000.00")


def test_a_tampered_checkpoint_refuses_to_load(serializer):

    """Flipping one byte of ciphertext fails the load rather than resuming an altered instruction."""

    type_name, blob = serializer.dumps_typed(PENDING_CHANGE)

    tampered = bytearray(blob)
    tampered[-1] ^= 0x01

    with pytest.raises(ValueError):
        serializer.loads_typed((type_name, bytes(tampered)))


def test_another_key_cannot_read_a_checkpoint(serializer):

    """A checkpoint written under one key is unreadable under another, which is why rotation is a migration."""

    stored = serializer.dumps_typed(PENDING_CHANGE)

    with pytest.raises(ValueError):
        EncryptedSerializer("a-different-key").loads_typed(stored)


def test_each_write_uses_a_fresh_nonce(serializer):

    """The same object encrypted twice produces different bytes, so identical pending changes are not linkable."""

    first, second = serializer.dumps_typed(PENDING_CHANGE)[1], serializer.dumps_typed(PENDING_CHANGE)[1]

    assert first != second
