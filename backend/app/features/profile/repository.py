"""Database reads and writes for the user's profile and their family members."""

from typing import Any

from app.db.models import FamilyMember, User
from app.features.profile.schemas import FamilyMemberCreate
from app.features.records.base_repository import BaseUserRecordRepository


class ProfileRepository(BaseUserRecordRepository):

    """Profile and family member queries on top of the shared user record queries."""

    async def get_user(self, user_id: int) -> User | None:

        """Return the user's own row."""

        return await self.session.get(User, user_id)

    async def update_profile(self, user_id: int, fields: dict[str, Any]) -> User | None:

        """Set the given profile fields on the user's row and flush, or return None when there is no row."""

        user = await self.get_user(user_id)

        if user is None:
            return None

        for name, value in fields.items():
            setattr(user, name, value)

        await self.session.flush()

        return user

    async def find_family_member(self, user_id: int, member: FamilyMemberCreate) -> FamilyMember | None:

        """Return this user's family member with the same name and relation, ignoring case."""

        return await self.find_match(FamilyMember, user_id, {"name": member.name, "relation": member.relation})

    async def add_family_member(self, user_id: int, member: FamilyMemberCreate) -> FamilyMember:

        """Insert a family member for the user and flush, so the database gives it an id."""

        return await self.insert(FamilyMember, user_id, member.model_dump())
