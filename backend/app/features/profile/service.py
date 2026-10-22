"""Business rules for changing the user's profile and adding family members."""

from app.db.models import FamilyMember
from app.features.profile.exceptions import ProfileError, UserNotFound
from app.features.profile.repository import ProfileRepository
from app.features.profile.schemas import FamilyMemberCreate, ProfileUpdate
from app.features.records.exceptions import RecordExists
from app.features.records.service import BaseRecordService


PROFILE_FIELDS = ("date_of_birth", "city", "risk_appetite", "retirement_age")

BASIC_FIELDS = ("name", "email", "date_of_birth", "city", "risk_appetite", "retirement_age", "life_expectancy")


class ProfileService(BaseRecordService[ProfileRepository]):

    """The steps behind the profile tools for one session."""

    repository_class = ProfileRepository

    async def get_profile(self, user_id: int) -> dict[str, str]:

        """Return the user's filled-in basic details as plain text values, or an empty dict when there is no row."""

        user = await self.repo.get_user(user_id)

        if user is None:
            return {}

        fields = {name: getattr(user, name) for name in BASIC_FIELDS}

        return {name: str(getattr(value, "value", value)) for name, value in fields.items() if value is not None}

    async def update_profile(self, user_id: int, changes: ProfileUpdate) -> dict:

        """Save the fields that were given and return them, refusing a life expectancy not above retirement age."""

        fields = changes.model_dump(exclude_none=True)

        if not fields:
            raise ProfileError("Nothing to update.")

        user = await self.repo.get_user(user_id)

        if user is None:
            raise UserNotFound("Your account could not be found.")

        retirement_age = fields.get("retirement_age", user.retirement_age)
        life_expectancy = fields.get("life_expectancy", user.life_expectancy)

        if retirement_age is not None and life_expectancy <= retirement_age:
            raise ProfileError(
                f"Life expectancy ({life_expectancy}) must be greater than retirement age ({retirement_age})."
                )

        user = await self.repo.update_profile(user_id, fields)

        if all(getattr(user, name) is not None for name in PROFILE_FIELDS):
            await self.mark_provided(user_id, "profile")

        return fields

    async def add_family_member(self, user_id: int, member: FamilyMemberCreate) -> FamilyMember:

        """Add the member unless one with the same name and relation is already saved."""

        existing = await self.repo.find_family_member(user_id, member)

        if existing is not None:
            raise RecordExists("family member", existing.id)

        record = await self.repo.add_family_member(user_id, member)

        await self.mark_provided(user_id, "family")

        return record
