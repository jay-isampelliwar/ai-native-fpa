"""Finding memory candidates in one run's messages."""

from app.db.models import Message
from app.features.memory.schemas import MemoryCandidate


async def extract_candidates(messages: list[Message]) -> list[MemoryCandidate]:

    """Return the memories worth keeping from one run's user and assistant messages."""

    # TODO(memory): Phase 6 replaces this with the LLM extractor and the memory rules.
    return []
