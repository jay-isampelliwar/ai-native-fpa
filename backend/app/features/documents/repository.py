"""Database reads and writes for documents, their parsed rows and the shared layout mappings."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, ImportRow, LayoutMapping


class DocumentRepository:

    """All document queries for one unit of work, sharing the caller's session."""

    def __init__(self, session: AsyncSession) -> None:

        """Keep the caller's session."""

        self.session = session

    async def find_by_hash(
        self,
        user_id: int,
        sha256: str
        ) -> Document | None:

        """The user's earlier upload of the same file, if any."""

        return await self.session.scalar(
            select(Document).where(Document.user_id == user_id, Document.sha256 == sha256)
            )

    async def get(
        self,
        user_id: int,
        document_id: int
        ) -> Document | None:

        """One of the user's documents, or None when it is not theirs or does not exist."""

        return await self.session.scalar(
            select(Document).where(Document.user_id == user_id, Document.id == document_id)
            )

    async def list_for_user(self, user_id: int) -> list[Document]:

        """The user's documents, newest first."""

        result = await self.session.scalars(
            select(Document).where(Document.user_id == user_id).order_by(Document.created_at.desc())
            )

        return list(result)

    def add(self, document: Document) -> None:

        """Add a new document to the session."""

        self.session.add(document)

    async def rows(self, document_id: int) -> list[ImportRow]:

        """The parsed rows of one document in file order."""

        result = await self.session.scalars(
            select(ImportRow).where(ImportRow.document_id == document_id).order_by(ImportRow.row_number)
            )

        return list(result)

    async def replace_rows(
        self,
        document_id: int,
        rows: list[ImportRow]
        ) -> None:

        """Swap a document's parsed rows for a fresh set, so parsing again never leaves old rows behind."""

        await self.session.execute(delete(ImportRow).where(ImportRow.document_id == document_id))
        self.session.add_all(rows)

    async def mappings(self, fingerprints: list[str]) -> dict[str, LayoutMapping]:

        """The saved mappings for these sheet shapes, by fingerprint."""

        if not fingerprints:
            return {}

        result = await self.session.scalars(
            select(LayoutMapping).where(LayoutMapping.fingerprint.in_(fingerprints))
            )

        return {mapping.fingerprint: mapping for mapping in result}

    async def save_proposal(
        self,
        fingerprint: str,
        headers: list[str],
        target_table: str | None,
        columns: dict[str, Any],
        reason: str | None
        ) -> None:

        """Keep the model's unconfirmed mapping for a shape, unless one is already saved."""

        await self.session.execute(
            insert(LayoutMapping)
            .values(fingerprint=fingerprint, headers=headers, target_table=target_table, columns=columns, reason=reason)
            .on_conflict_do_nothing(index_elements=["fingerprint"])
            )

    async def confirm(
        self,
        fingerprint: str,
        headers: list[str],
        target_table: str | None,
        columns: dict[str, Any],
        user_id: int
        ) -> None:

        """Save the mapping the user confirmed for a shape, replacing any proposal."""

        now = datetime.now(UTC)
        values = {
            "headers": headers,
            "target_table": target_table,
            "columns": columns,
            "confirmed_by": user_id,
            "confirmed_at": now,
            "updated_at": now,
            }

        await self.session.execute(
            insert(LayoutMapping)
            .values(fingerprint=fingerprint, **values)
            .on_conflict_do_update(index_elements=["fingerprint"], set_=values)
            )
