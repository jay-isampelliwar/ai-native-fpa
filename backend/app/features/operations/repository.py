"""Database reads and writes for saved tool operations."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ToolOperation


class OperationRepository:

    """All tool operation queries, sharing the write's own session so the operation commits with the write."""

    def __init__(self, session: AsyncSession) -> None:

        """Keep the write's session."""

        self.session = session

    async def find(self, conversation_id: int, tool_call_id: str) -> ToolOperation | None:

        """Return the saved operation for this tool call in this conversation, if it already committed."""

        query = select(ToolOperation).where(
            ToolOperation.conversation_id == conversation_id,
            ToolOperation.tool_call_id == tool_call_id,
            )

        return await self.session.scalar(query)

    def add(
        self,
        user_id: int,
        conversation_id: int,
        run_id: int | None,
        tool_call_id: str,
        tool_name: str,
        arguments_hash: str,
        result: dict[str, Any],
        ) -> None:

        """Add the operation to the write's session, so it is saved by the same commit as the write."""

        self.session.add(
            ToolOperation(
                user_id=user_id,
                conversation_id=conversation_id,
                run_id=run_id,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                arguments_hash=arguments_hash,
                result=result,
                )
            )
