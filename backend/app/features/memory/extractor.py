"""Finding memory candidates in one run's messages with the LLM, then checking them against the memory rules."""

from app.core.config import get_settings
from app.db.enums import MessageRole
from app.db.models import MemoryItem, Message
from app.features.memory.prompt import build_prompt
from app.features.memory.rules import apply_rules
from app.features.memory.schemas import ExtractionResult, MemoryCandidate
from app.services.llm import llm_service


async def extract_candidates(
    messages: list[Message],
    memories: list[MemoryItem],
    ) -> list[MemoryCandidate]:

    """Ask the memory model for memories in this run, given the user's current ones, and keep those that pass the rules."""

    user_message_ids = {message.id for message in messages if message.role == MessageRole.user}

    if not user_message_ids:
        return []

    model = llm_service.get_model(get_settings().MEMORY_MODEL).with_structured_output(
        ExtractionResult,
        method="function_calling",
        )

    result = await model.ainvoke(build_prompt(messages, memories))

    return apply_rules(result.memories, user_message_ids)
