"""Database reads and writes for insurance policies."""

from typing import Any

from app.db.models import InsurancePolicy
from app.features.records.base_repository import BaseUserRecordRepository


class ProtectionRepository(BaseUserRecordRepository):

    """Insurance queries on top of the shared user record queries."""

    async def add_policy(self, user_id: int, fields: dict[str, Any]) -> InsurancePolicy:

        """Insert an insurance policy for the user."""

        return await self.insert(InsurancePolicy, user_id, fields)
