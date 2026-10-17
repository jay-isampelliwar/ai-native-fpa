"""The memory rules: which proposed memories are kept, and with which status."""

from decimal import Decimal

from app.db.enums import MemoryStatus
from app.features.memory.schemas import ExtractedMemory, MemoryCandidate


ALLOWED_TYPES = frozenset({"preference", "episodic"})

ALLOWED_NAMESPACES = frozenset({
    "investment_preferences",
    "communication_preferences",
    "financial_attitudes",
    "life_events",
    "past_decisions",
    })

BLOCKED_KEY_PARTS = (
    "risk_appetite",
    "risk_tolerance",
    "risk_profile",
    "retirement_age",
    "income",
    "salary",
    "expense",
    "balance",
    "net_worth",
    "asset",
    "liabilit",
    "loan",
    "insurance",
    "tax",
    "currency",
    "holding",
    "price",
    )

ACTIVE_CONFIDENCE = Decimal("0.8")

MIN_CONFIDENCE = Decimal("0.5")


def is_blocked_key(memory_key: str) -> bool:

    """Return True if the key names data the structured financial tables already own."""

    key = memory_key.lower()

    return any(part in key for part in BLOCKED_KEY_PARTS)


def decide_status(
    confidence: Decimal,
    explicit: bool,
    ) -> MemoryStatus | None:

    """Return active for explicit and sure, candidate for inferred or less sure, or None to drop it."""

    if confidence < MIN_CONFIDENCE:
        return None

    if explicit and confidence >= ACTIVE_CONFIDENCE:
        return MemoryStatus.active

    return MemoryStatus.candidate


def to_candidate(
    proposed: ExtractedMemory,
    user_message_ids: set[int],
    ) -> MemoryCandidate | None:

    """Check one proposed memory against every rule and return it as a candidate, or None if any rule fails."""

    if proposed.memory_type not in ALLOWED_TYPES or proposed.namespace not in ALLOWED_NAMESPACES:
        return None

    if not proposed.memory_key or is_blocked_key(proposed.memory_key) or not proposed.content:
        return None

    if proposed.source_message_id not in user_message_ids:
        return None

    confidence = Decimal(str(round(min(max(proposed.confidence, 0.0), 1.0), 4)))

    status = decide_status(confidence, proposed.explicit)

    if status is None:
        return None

    return MemoryCandidate(
        memory_type=proposed.memory_type,
        namespace=proposed.namespace,
        memory_key=proposed.memory_key.lower(),
        content=proposed.content,
        confidence=confidence,
        status=status,
        source_message_id=proposed.source_message_id,
        )


def apply_rules(
    proposed: list[ExtractedMemory],
    user_message_ids: set[int],
    ) -> list[MemoryCandidate]:

    """Keep the proposed memories that pass every rule, one per namespace and key, the most confident winning."""

    kept: dict[tuple[str, str | None], MemoryCandidate] = {}

    for memory in proposed:

        candidate = to_candidate(memory, user_message_ids)

        if candidate is None:
            continue

        slot = (candidate.namespace, candidate.memory_key)
        current = kept.get(slot)

        if current is None or candidate.confidence > current.confidence:
            kept[slot] = candidate

    return list(kept.values())
