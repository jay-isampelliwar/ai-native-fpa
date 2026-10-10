"""Response bodies for the conversations routes."""

from datetime import datetime

from pydantic import BaseModel

from app.db.enums import MessageRole, MessageStatus, RunStatus


class ConversationSummary(BaseModel):

    """One row of the history list: the chat's id, title and when it last changed."""

    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationList(BaseModel):

    """The user's chats, most recently active first."""

    conversations: list[ConversationSummary]


class MessageOut(BaseModel):

    """One user or assistant message as the chat shows it."""

    id: int
    run_id: int | None
    role: MessageRole
    status: MessageStatus
    text: str
    created_at: datetime


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
