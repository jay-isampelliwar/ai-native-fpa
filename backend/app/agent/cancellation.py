"""The check the agent makes before each model call and tool call, so a run asked to stop stops even when its task could not be reached."""

from sqlalchemy import select

from app.db.enums import RunStatus
from app.db.models import AgentRun
from app.db.session import SessionLocal


class RunCancelled(Exception):

    """The run was asked to stop, seen in its saved status."""

    def __init__(self, run_id: int) -> None:

        """Keep the id of the run that was asked to stop."""

        super().__init__(f"run {run_id} was asked to stop")

        self.run_id = run_id


async def stop_if_cancelled(run_id: int | None) -> None:

    """Raise RunCancelled when the run's saved status says a stop was asked for."""

    if run_id is None:
        return

    async with SessionLocal() as session:
        status = await session.scalar(select(AgentRun.status).where(AgentRun.id == run_id))

    if status == RunStatus.cancel_requested:
        raise RunCancelled(run_id)
