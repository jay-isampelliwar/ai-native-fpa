"""The conversations routes: list the user's chats, open one with its messages, rename one, and soft delete one."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.enums import MessageRole
from app.db.session import get_session
from app.features.conversations.repository import ConversationRepository
from app.features.conversations.schemas import (
    ActiveRun,
    ConversationDetail,
    ConversationList,
    ConversationRename,
    ConversationSummary,
    MessageOut,
    )
from app.features.conversations.titles import title_from


router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
    ) -> ConversationList:

    """Return the user's chats for the history list, most recently active first."""

    rows = await ConversationRepository(session).list_for_user(user_id, limit)

    conversations = [
        ConversationSummary(
            id=conversation.id,
            title=conversation.title or title_from(first_message),
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            )
        for conversation, first_message in rows
        ]

    return ConversationList(conversations=conversations)


@router.patch("/{conversation_id}")
async def rename_conversation(
    conversation_id: int,
    body: ConversationRename,
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
    ) -> ConversationSummary:

    """Give one chat a new title, keeping its place in the history list."""

    repo = ConversationRepository(session)

    conversation = await repo.get_for_user(conversation_id, user_id)

    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    await repo.rename(conversation, body.title)

    await session.commit()

    return ConversationSummary(
        id=conversation.id,
        title=body.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: int,
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
    ) -> None:

    """Soft delete one chat so it leaves the history list, refusing while a reply is still being written."""

    repo = ConversationRepository(session)

    conversation = await repo.get_for_user(conversation_id, user_id)

    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    if await repo.get_active_run(conversation_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Wait for the reply to finish before deleting this chat")

    await repo.soft_delete(conversation)

    await session.commit()


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: int,
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
    ) -> ConversationDetail:

    """Return one chat with its messages and the run still writing a reply, if any."""

    repo = ConversationRepository(session)

    conversation = await repo.get_for_user(conversation_id, user_id)

    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    messages = await repo.list_messages(conversation_id)

    run = await repo.get_active_run(conversation_id)

    first_user_text = next((message.content.get("text") for message in messages if message.role == MessageRole.user), None)

    return ConversationDetail(
        id=conversation.id,
        title=conversation.title or title_from(first_user_text),
        messages=[
            MessageOut(
                id=message.id,
                run_id=message.run_id,
                role=message.role,
                status=message.status,
                text=message.content.get("text", ""),
                created_at=message.created_at,
                )
            for message in messages
            ],
        active_run=ActiveRun(run_id=run.id, status=run.status) if run is not None else None,
        )
