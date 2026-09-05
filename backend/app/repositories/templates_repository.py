"""Storage for learned import templates, which is what stops an unknown format being a recurring cost.

A template confirmed by a person is stored against the fingerprint of the layout it was confirmed for.
The next file with that fingerprint is parsed by that mapping without anyone being asked, which is the
whole economics of the design: unfamiliar formats cost one confirmation, not one every month.

Fingerprints are unique. Two confirmations of the same layout are the same template, and the second
updates the first rather than creating a rival mapping that would make parsing depend on which row the
query happened to return.

``times_used`` is incremented on every match. A template nobody uses is a candidate for review, and one
used heavily is a candidate for promotion into the built in set where it can be tested.

Learned templates are per installation, not per user, because a layout is a property of a provider
rather than of a person. ``created_by_user_id`` records who confirmed it so a bad mapping can be traced,
but any user uploading that layout benefits from it.

Nothing here decides whether a mapping is correct. Validation happens before a mapping is offered for
confirmation, and the confirmation itself is a person's judgement.
"""

from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import session_scope
from app.extraction.templates import SheetSpec, TemplateSpec
from app.models.orm.imports import ImportTemplateRow


class TemplatesRepository:

    """Stores and retrieves the column mappings people have confirmed for particular layouts."""

    async def by_fingerprint(self, fingerprint: str) -> TemplateSpec | None:

        """Find a confirmed template for this exact layout, which is how a known file skips the mapping step."""

        async with session_scope() as session:

            row = await session.scalar(
                select(ImportTemplateRow).where(
                    ImportTemplateRow.fingerprint == fingerprint,
                    ImportTemplateRow.confirmed.is_(True),
                )
            )

            if row is None:
                return None

            await session.execute(
                update(ImportTemplateRow)
                .where(ImportTemplateRow.id == row.id)
                .values(times_used=ImportTemplateRow.times_used + 1)
            )

            return self._to_spec(row)

    async def save(
        self,
        session: AsyncSession,
        fingerprint: str,
        name: str,
        provider: str,
        sheets: list[dict],
        created_by_user_id: int,
        document_kind: str = "holdings_statement",
        ) -> ImportTemplateRow:

        """Store a confirmed mapping against its layout, replacing any earlier mapping for the same one."""

        existing = await session.scalar(
            select(ImportTemplateRow).where(ImportTemplateRow.fingerprint == fingerprint)
        )

        if existing is not None:

            existing.name = name
            existing.provider = provider
            existing.column_mapping = {"sheets": sheets}
            existing.confirmed = True
            existing.created_by_user_id = created_by_user_id

            return existing

        row = ImportTemplateRow(
            id=f"tpl_{uuid4().hex[:12]}",
            name=name,
            provider=provider,
            document_kind=document_kind,
            fingerprint=fingerprint,
            column_mapping={"sheets": sheets},
            builtin=False,
            confirmed=True,
            created_by_user_id=created_by_user_id,
        )

        session.add(row)

        await session.flush()

        return row

    def _to_spec(self, row: ImportTemplateRow) -> TemplateSpec:

        """Rebuild the in memory template from its stored mapping, so learned and built in parse identically."""

        return TemplateSpec(
            id=row.id,
            name=row.name,
            provider=row.provider,
            document_kind=row.document_kind,
            fingerprint=row.fingerprint,
            builtin=False,
            sheets=[SheetSpec(**sheet) for sheet in row.column_mapping.get("sheets", [])],
        )


templates_repository = TemplatesRepository()
