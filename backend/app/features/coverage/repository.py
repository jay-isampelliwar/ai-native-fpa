"""Database reads and writes for the user's one data_coverage row."""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import CoverageStatus
from app.db.models import DataCoverage


class CoverageRepository:

    """Coverage queries for one session; the row is created the first time it is needed."""

    def __init__(self, session: AsyncSession) -> None:

        """Keep the session the caller opened, so every method talks through it."""

        self.session = session

    async def get_or_create(self, user_id: int) -> DataCoverage:

        """Return the user's coverage row, inserting one with every section pending when there is none."""

        await self.session.execute(
            insert(DataCoverage).values(user_id=user_id).on_conflict_do_nothing(index_elements=["user_id"])
            )

        return await self.session.get(DataCoverage, user_id, populate_existing=True)

    async def set_statuses(self, user_id: int, statuses: dict[str, CoverageStatus]) -> DataCoverage:

        """Set the given section statuses on the user's row and flush."""

        coverage = await self.get_or_create(user_id)

        for section, status in statuses.items():
            setattr(coverage, section, status)

        await self.session.flush()

        return coverage
