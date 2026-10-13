"""Request and response bodies for the conversations routes."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.db.enums import MessageRole, MessageStatus, RunStatus


class ConversationRename(BaseModel):

    """The new title the user typed for one chat, with outer spaces removed."""

    title: str = Field(min_length=1, max_length=255)

    @field_validator("title")
    @classmethod
    def tidy_title(cls, value: str) -> str:

        """Join the words with single spaces and refuse a title that is only spaces."""

        value = " ".join(value.split())

        if not value:
            raise ValueError("Title cannot be empty")

        return value


class ConversationSummary(BaseModel):

    """One row of the history list: the chat's id, title and when it last changed."""

    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationList(BaseModel):

    """The user's chats, most recently active first."""

    conversations: list[ConversationSummary]


class ToolStepOut(BaseModel):

    """One tool the planner called for an answer, with the line the chat shows and how it ended."""

    id: str
    name: str
    label: str
    status: Literal["running", "ok", "error", "stopped"]


class MessageOut(BaseModel):

    """One user or assistant message as the chat shows it, with the tools behind it."""

    id: int
    run_id: int | None
    role: MessageRole
    status: MessageStatus
    text: str
    created_at: datetime
    tools: list[ToolStepOut] = []


class ActiveRun(BaseModel):

    """The run still writing a reply in this chat, so the frontend can rejoin its stream."""

    run_id: int
    status: RunStatus


class ConversationDetail(BaseModel):

    """One chat with its messages in order and the run still in progress, if any."""

    id: int
    title: str
    messages: list[MessageOut]
    active_run: ActiveRun | None
