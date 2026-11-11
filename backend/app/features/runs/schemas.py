"""Request and response bodies for the runs routes."""

from typing import Any, Self

from pydantic import BaseModel, Field, model_validator

from app.agent.forms import FormKind, form_text, known_values
from app.db.enums import RunStatus
from app.db.models import AgentRun


class FormSubmission(BaseModel):

    """A filled form the user sent: which form, its values, the item it changes, and the card that opened it."""

    kind: FormKind
    values: dict[str, Any] = Field(default_factory=dict)
    record_id: int | None = None
    block_id: str | None = Field(default=None, max_length=255)

    def saved(self) -> dict[str, Any]:

        """The form as kept on the user message, with only the fields this form has."""

        return {
            "kind": self.kind.value,
            "values": known_values(self.kind, self.values),
            "record_id": self.record_id,
            "block_id": self.block_id,
            }


MAX_ATTACHED_DOCUMENTS = 10


class CreateRunRequest(BaseModel):

    """One user message or filled form to start a run, with the id the frontend made for retries."""

    conversation_id: int | None = None
    client_request_id: str = Field(min_length=1, max_length=255)
    message: str = ""
    form: FormSubmission | None = None
    document_ids: list[int] = Field(default_factory=list, max_length=MAX_ATTACHED_DOCUMENTS)

    @model_validator(mode="after")
    def text_or_form(self) -> Self:

        """Refuse a request with no message, form or attached file, and write a form as the message the agent reads."""

        if self.form is not None:
            self.message = form_text(self.form.kind, self.form.values, self.form.record_id)

        if not self.message.strip() and not self.document_ids:
            raise ValueError("Send a message, a form or a file")

        return self


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
