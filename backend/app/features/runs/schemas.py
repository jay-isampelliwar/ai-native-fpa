"""Request and response bodies for the runs routes."""

from typing import Self

from pydantic import BaseModel, Field

from app.db.enums import RunStatus
from app.db.models import AgentRun


class CreateRunRequest(BaseModel):

    """One user message to start a run, with the id the frontend made for retries."""

    conversation_id: int | None = None
    client_request_id: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1)


class RunResponse(BaseModel):

    """The run the backend created or found, and the conversation it belongs to."""

    run_id: int
    conversation_id: int
    status: RunStatus

    @classmethod
    def from_run(cls, run: AgentRun) -> Self:

        """Build the response body from a run row."""

        return cls(
            run_id=run.id,
            conversation_id=run.conversation_id,
            status=run.status,
            )
