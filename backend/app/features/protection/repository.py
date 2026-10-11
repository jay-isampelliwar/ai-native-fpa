"""Database reads and writes for insurance policies."""

from typing import Any

from app.db.enums import PolicyType
from app.db.models import InsurancePolicy
from app.features.records.base_repository import BaseUserRecordRepository


class ProtectionRepository(BaseUserRecordRepository):

    """Insurance queries on top of the shared user record queries."""

    async def find_policy(
        self,
        user_id: int,
        policy_type: PolicyType,
        insurer: str,
        family_member_id: int | None,
        ) -> InsurancePolicy | None:

        """Return the user's policy of the same type from the same insurer for the same person."""

        return await self.find_match(
            InsurancePolicy,
            user_id,
            {"policy_type": policy_type, "insurer": insurer, "family_member_id": family_member_id},
            )

    async def add_policy(self, user_id: int, fields: dict[str, Any]) -> InsurancePolicy:

        """Insert an insurance policy for the user."""

        return await self.insert(InsurancePolicy, user_id, fields)
