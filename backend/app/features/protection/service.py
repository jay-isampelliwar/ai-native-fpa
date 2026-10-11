"""Business rules for adding insurance policies."""

from app.db.models import InsurancePolicy
from app.features.protection.repository import ProtectionRepository
from app.features.protection.schemas import InsurancePolicyCreate
from app.features.records.exceptions import RecordExists
from app.features.records.service import BaseRecordService


class ProtectionService(BaseRecordService[ProtectionRepository]):

    """The steps behind the insurance tool for one session."""

    repository_class = ProtectionRepository

    async def add_policy(self, user_id: int, policy: InsurancePolicyCreate) -> InsurancePolicy:

        """Link the named family member, then add the policy unless the same one is already saved."""

        member_id = await self.family_member_id(user_id, policy.family_member_name)

        existing = await self.repo.find_policy(user_id, policy.policy_type, policy.insurer, member_id)

        if existing is not None:
            raise RecordExists("insurance policy", existing.id)

        fields = policy.model_dump(exclude={"family_member_name"})

        record = await self.repo.add_policy(user_id, {**fields, "family_member_id": member_id})

        await self.mark_provided(user_id, "insurance")

        await self.session.commit()

        return record
