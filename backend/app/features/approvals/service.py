"""Business rules for deciding an approval and carrying on its paused run, whether the user, a new message, a cancel or the clock decided it."""

from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.approval import APPROVE, CANCEL, REJECT
from app.db.enums import ApprovalStatus, RunStatus, ToolCallStatus
from app.db.models import ToolApproval, ToolCall
from app.features.approvals.exceptions import ApprovalExpired, ApprovalNotFound, ApprovalNotPending
from app.features.approvals.repository import ApprovalRepository
from app.features.approvals.schemas import ApprovalChoice
from app.features.runs.registry import run_registry
from app.features.runs.repository import RunRepository
from app.features.runs.schemas import RunResponse
from app.features.runs.worker import resume_run


@dataclass(frozen=True)
class Closing:

    """How one way of deciding an approval moves the approval, answers the gate and ends the run."""

    status: ApprovalStatus
    decision: str
    reply: bool
    final_status: RunStatus
    reason: str


USER_APPROVED = Closing(ApprovalStatus.approved, APPROVE, True, RunStatus.completed, "user")
USER_REJECTED = Closing(ApprovalStatus.rejected, REJECT, True, RunStatus.completed, "user")
NEW_MESSAGE = Closing(ApprovalStatus.rejected, REJECT, False, RunStatus.completed, "new_message")
EXPIRED = Closing(ApprovalStatus.expired, REJECT, False, RunStatus.cancelled, "expired")
CANCELLED = Closing(ApprovalStatus.cancelled, CANCEL, False, RunStatus.cancelled, "cancelled")

USER_CLOSINGS = {ApprovalChoice.approve: USER_APPROVED, ApprovalChoice.reject: USER_REJECTED}


class ApprovalService:

    """The steps behind deciding one approval, sharing the caller's session."""

    def __init__(self, session: AsyncSession) -> None:

        """Keep the caller's session and build the repositories on top of it."""

        self.session = session
        self.approvals = ApprovalRepository(session)
        self.runs = RunRepository(session)

    async def submit(
        self,
        run_id: int,
        approval_id: int,
        user_id: int,
        choice: ApprovalChoice,
        ) -> RunResponse:

        """Apply the user's click to their pending approval and carry on the run in the background."""

        approval = await self.approvals.lock_for_user(approval_id, user_id)

        if approval is None or approval.run_id != run_id:
            raise ApprovalNotFound(approval_id)

        if approval.status != ApprovalStatus.pending:
            raise ApprovalNotPending(approval_id)

        if approval.expires_at <= datetime.now(UTC):

            await self.close(approval, EXPIRED)

            raise ApprovalExpired(approval_id)

        resume = await self.decide(approval, USER_CLOSINGS[choice])

        if resume is not None:
            run_registry.start(run_id, resume)

        run = await self.runs.get_run_for_user(run_id, user_id)

        return RunResponse.from_run(run)

    async def close_pending_in(self, conversation_id: int, closing: Closing) -> None:

        """Decide the conversation's pending approval, if any, without the user, and wait for its run to end."""

        approval = await self.approvals.lock_pending_for_conversation(conversation_id)

        if approval is None:
            return

        await self.close(approval, closing)

    async def close(self, approval: ToolApproval, closing: Closing) -> None:

        """Decide a locked approval without the user and wait for its run to end, so nothing else starts on the thread first."""

        resume = await self.decide(approval, closing)

        if resume is not None:
            await resume

    async def decide(
        self,
        approval: ToolApproval,
        closing: Closing,
        ) -> Coroutine[Any, Any, None] | None:

        """Commit the decision with the run back to running, and return the resume work, or None if the run was no longer paused."""

        await self.approvals.decide(approval, closing.status, {"decision": closing.decision, "reason": closing.reason})

        call = await self.session.get(ToolCall, approval.tool_call_id)

        moved = await self.runs.set_run_status(approval.run_id, [RunStatus.awaiting_approval], RunStatus.running)

        if moved and closing.status == ApprovalStatus.approved:

            await self.runs.set_tool_call_status(
                approval.conversation_id,
                call.tool_call_id,
                [ToolCallStatus.awaiting_approval],
                ToolCallStatus.running,
                )

        message = await self.runs.get_assistant_message(approval.run_id)

        await self.session.commit()

        if not moved:
            return None

        answer = {
            "decision": closing.decision,
            "tool_call_id": call.tool_call_id,
            "arguments": approval.arguments,
            "reply": closing.reply,
            }

        return resume_run(
            approval.run_id,
            approval.conversation_id,
            approval.user_id,
            message.id,
            answer,
            closing.final_status,
            )
