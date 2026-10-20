"""Database reads and writes for tool approvals."""

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ApprovalStatus
from app.db.models import ToolApproval, ToolCall


APPROVAL_TTL = timedelta(minutes=15)


class ApprovalRepository:

    """All approval queries for one unit of work, sharing the caller's session so a decision commits with its run change."""

    def __init__(self, session: AsyncSession) -> None:

        """Keep the caller's session."""

        self.session = session

    async def add_pending(
        self,
        user_id: int,
        conversation_id: int,
        run_id: int,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        preview: dict[str, Any],
        ) -> ToolApproval:

        """Add a pending approval for one saved tool call, expiring APPROVAL_TTL from now, without committing."""

        tool_call_row_id = await self.session.scalar(
            select(ToolCall.id).where(
                ToolCall.conversation_id == conversation_id,
                ToolCall.tool_call_id == tool_call_id,
                )
            )

        approval = ToolApproval(
            user_id=user_id,
            conversation_id=conversation_id,
            run_id=run_id,
            tool_call_id=tool_call_row_id,
            tool_name=tool_name,
            arguments=arguments,
            preview=preview,
            expires_at=func.now() + APPROVAL_TTL,
            )

        self.session.add(approval)

        await self.session.flush()

        await self.session.refresh(approval)

        return approval

    async def lock_for_user(self, approval_id: int, user_id: int) -> ToolApproval | None:

        """Lock one approval this user owns until the commit, so a double click waits and then sees it decided."""

        query = (
            select(ToolApproval)
            .where(ToolApproval.id == approval_id, ToolApproval.user_id == user_id)
            .with_for_update()
            )

        return await self.session.scalar(query)

    async def lock_pending_for_conversation(self, conversation_id: int) -> ToolApproval | None:

        """Lock the conversation's pending approval, if any, so a new message can reject it."""

        query = (
            select(ToolApproval)
            .where(
                ToolApproval.conversation_id == conversation_id,
                ToolApproval.status == ApprovalStatus.pending,
                )
            .with_for_update()
            )

        return await self.session.scalar(query)

    async def pending_for_run(self, run_id: int) -> ToolApproval | None:

        """Return the run's pending approval, to show its card again after a refresh."""

        query = select(ToolApproval).where(
            ToolApproval.run_id == run_id,
            ToolApproval.status == ApprovalStatus.pending,
            )

        return await self.session.scalar(query)

    async def lock_expired(self, limit: int) -> list[ToolApproval]:

        """Lock up to limit pending approvals past their expiry, skipping rows a click or another sweep already holds."""

        query = (
            select(ToolApproval)
            .where(
                ToolApproval.status == ApprovalStatus.pending,
                ToolApproval.expires_at <= func.now(),
                )
            .order_by(ToolApproval.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
            )

        return list(await self.session.scalars(query))

    async def decide(
        self,
        approval: ToolApproval,
        status: ApprovalStatus,
        decision: dict[str, Any],
        ) -> None:

        """Mark a locked approval with its final status and what decided it, without committing."""

        approval.status = status
        approval.decision = decision
        approval.decided_at = func.now()

        await self.session.flush()
