"""The idempotency guard for write tools: do the write once per tool call, and give back its saved result if the call runs again."""

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage, ToolCall
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context import PlannerContext
from app.agent.tools.limits import tool_session
from app.agent.tools.results import ToolResult, conflict, from_record_error, from_validation_error, mismatch, unverified
from app.agent.tools.verify import SaveMismatch
from app.db.models import ToolOperation
from app.db.session import SessionLocal
from app.features.operations.repository import OperationRepository
from app.features.records.exceptions import RecordError


type WriteWork = Callable[[AsyncSession], Awaitable[ToolResult]]

MISMATCH_TEXT = "This tool call was already used with different details, so nothing was changed."


@dataclass(frozen=True)
class OperationKey:

    """Who made the call, in which conversation and run, and the call itself, as the guard stores it."""

    user_id: int
    conversation_id: int
    run_id: int | None
    tool_call_id: str
    tool_name: str
    arguments_hash: str


def arguments_hash(arguments: dict[str, Any]) -> str:

    """A stable fingerprint of the arguments the model sent, the same however the keys are ordered."""

    text = json.dumps(arguments, sort_keys=True, default=str, separators=(",", ":"))

    return hashlib.sha256(text.encode()).hexdigest()


def current_call(runtime: ToolRuntime[PlannerContext]) -> ToolCall | None:

    """Find the call this tool is running for, with its name and arguments, in the model's latest tool request."""

    messages = (runtime.state or {}).get("messages", [])

    for message in reversed(messages):

        if not isinstance(message, AIMessage):
            continue

        for call in message.tool_calls:

            if call["id"] == runtime.tool_call_id:
                return call

    return None


def operation_key(runtime: ToolRuntime[PlannerContext]) -> OperationKey | None:

    """The key for this call, or None outside a conversation, where nothing can be replayed."""

    call = current_call(runtime)
    context = runtime.context

    if call is None or context.conversation_id is None:
        return None

    return OperationKey(
        user_id=context.user_id,
        conversation_id=context.conversation_id,
        run_id=context.run_id,
        tool_call_id=call["id"],
        tool_name=call["name"],
        arguments_hash=arguments_hash(call["args"]),
        )


def replayed(saved: ToolOperation, key: OperationKey) -> ToolResult:

    """The first result again for the same call with the same arguments, and a conflict if the arguments changed."""

    if saved.arguments_hash != key.arguments_hash:
        return conflict("idempotency_mismatch", MISMATCH_TEXT)

    return ToolResult.model_validate(saved.result)


async def saved_result(key: OperationKey | None) -> ToolResult | None:

    """Read the call's saved result in a fresh session, after a commit lost the race to another run of the same call."""

    if key is None:
        return None

    async with SessionLocal() as session:
        saved = await OperationRepository(session).find(key.conversation_id, key.tool_call_id)

    return None if saved is None else replayed(saved, key)


async def run_write(
    runtime: ToolRuntime[PlannerContext],
    work: WriteWork,
    ) -> ToolResult:

    """Give back the saved result if this call already wrote, otherwise do the write, require its read-back check, and save its result in the same commit."""

    key = operation_key(runtime)

    try:

        async with tool_session(runtime.context) as session:

            operations = OperationRepository(session)

            if key is not None:

                saved = await operations.find(key.conversation_id, key.tool_call_id)

                if saved is not None:
                    return replayed(saved, key)

            result = await work(session)

            if result.status != "success":

                await session.rollback()

                return result

            if not result.verified:

                await session.rollback()

                return unverified()

            if key is not None:

                operations.add(
                    key.user_id,
                    key.conversation_id,
                    key.run_id,
                    key.tool_call_id,
                    key.tool_name,
                    key.arguments_hash,
                    result.model_dump(mode="json", exclude_none=True),
                    )

            await session.commit()

    except SaveMismatch as exc:
        return mismatch(exc.fields)

    except ValidationError as exc:
        return from_validation_error(exc)

    except RecordError as exc:
        return from_record_error(exc)

    except IntegrityError:

        winner = await saved_result(key)

        if winner is not None:
            return winner

        return conflict("clashes", "This clashes with another saved item.")

    return result
