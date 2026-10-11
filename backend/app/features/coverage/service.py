"""Business rules for reading what is still missing and for marking sections none, declined or pending."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import CoverageStatus
from app.db.models import DataCoverage, User
from app.features.coverage.repository import CoverageRepository
from app.features.coverage.schemas import CoverageChoice, MissingData
from app.features.profile.service import PROFILE_FIELDS
from app.features.records.exceptions import RecordError
from app.features.records.kinds import COVERAGE_MODELS


PROFILE = "profile"
SECTIONS = (PROFILE, *COVERAGE_MODELS)


class CoverageService:

    """The steps behind the coverage tools for one session."""

    def __init__(self, session: AsyncSession) -> None:

        """Keep the session and build the coverage repository on top of it."""

        self.session = session
        self.repo = CoverageRepository(session)

    async def section_has_data(self, user_id: int, section: str) -> bool:

        """Return True when the user has saved anything for this section."""

        if section == PROFILE:

            user = await self.session.get(User, user_id)

            return user is not None and any(getattr(user, name) is not None for name in PROFILE_FIELDS)

        model = COVERAGE_MODELS[section]

        count = await self.session.scalar(select(func.count()).select_from(model).where(model.user_id == user_id))

        return count > 0

    async def missing_profile_fields(self, user_id: int) -> list[str]:

        """Name the profile details the user has not given yet."""

        user = await self.session.get(User, user_id)

        if user is None:
            return []

        return [name.replace("_", " ") for name in PROFILE_FIELDS if getattr(user, name) is None]

    async def sync_provided(self, user_id: int, coverage: DataCoverage) -> None:

        """Mark pending sections as provided when data for them is already saved."""

        for section in SECTIONS:

            if getattr(coverage, section) != CoverageStatus.pending:
                continue

            if section == PROFILE:
                complete = not await self.missing_profile_fields(user_id)

            else:
                complete = await self.section_has_data(user_id, section)

            if complete:
                setattr(coverage, section, CoverageStatus.provided)

    async def missing(self, user_id: int) -> MissingData:

        """Return the sections still pending and the empty profile details, after syncing saved data."""

        coverage = await self.repo.get_or_create(user_id)

        await self.sync_provided(user_id, coverage)

        await self.session.commit()

        pending = [section for section in SECTIONS if getattr(coverage, section) == CoverageStatus.pending]

        return MissingData(
            pending_sections=pending,
            missing_profile_fields=await self.missing_profile_fields(user_id),
            )

    async def update(self, user_id: int, changes: dict[str, CoverageChoice]) -> dict[str, CoverageStatus]:

        """Set none, declined or pending on the given sections, refusing none or declined where data is saved."""

        if not changes:
            raise RecordError("Nothing to update.")

        unknown = [section for section in changes if section not in SECTIONS]

        if unknown:
            raise RecordError(f"Unknown sections: {', '.join(unknown)}. Valid sections: {', '.join(SECTIONS)}.")

        statuses = {}

        for section, choice in changes.items():

            if section == PROFILE and choice == CoverageChoice.none:
                raise RecordError("The profile cannot be none. Use declined if the user does not want to share it.")

            if choice != CoverageChoice.pending and await self.section_has_data(user_id, section):
                raise RecordError(
                    f"The user already has saved {section.replace('_', ' ')}. Ask whether to remove them before marking it {choice.value}."
                    )

            statuses[section] = CoverageStatus(choice.value)

        await self.repo.set_statuses(user_id, statuses)

        await self.session.commit()

        return statuses

    async def reset_if_empty(self, user_id: int, section: str) -> None:

        """Put a section back to pending when its last item was removed; the caller commits."""

        if not await self.section_has_data(user_id, section):
            await self.repo.set_statuses(user_id, {section: CoverageStatus.pending})
