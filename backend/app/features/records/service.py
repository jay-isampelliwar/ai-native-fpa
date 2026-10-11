"""Steps every record service shares: hold the session and repository, mark coverage, and look up a family member."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import CoverageStatus
from app.db.models import FamilyMember
from app.features.coverage.repository import CoverageRepository
from app.features.records.base_repository import BaseUserRecordRepository
from app.features.records.exceptions import FamilyMemberNotFound


class BaseRecordService[RepoT: BaseUserRecordRepository]:

    """The parent of every domain service, built on that domain's repository."""

    repository_class: type[RepoT]

    def __init__(self, session: AsyncSession) -> None:

        """Keep the session and build the domain repository on top of it."""

        self.session = session
        self.repo = self.repository_class(session)

    async def mark_provided(self, user_id: int, section: str) -> None:

        """Mark a coverage section as provided, whatever it was before, because data was just saved for it."""

        await CoverageRepository(self.session).set_statuses(user_id, {section: CoverageStatus.provided})

    async def family_member_id(self, user_id: int, name: str | None) -> int | None:

        """Return the id of the user's family member with this name, or None when no name was given."""

        if name is None:
            return None

        member = await self.repo.find_match(FamilyMember, user_id, {"name": name})

        if member is None:
            raise FamilyMemberNotFound(name)

        return member.id
