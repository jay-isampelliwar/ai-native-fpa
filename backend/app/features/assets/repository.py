"""Database reads and writes for bank accounts, deposits, retirement accounts and physical assets."""

from app.db.models import BankAccount, FixedDeposit, PhysicalAsset, RetirementAccount
from app.features.assets.schemas import (
    BankAccountCreate,
    FixedDepositCreate,
    PhysicalAssetCreate,
    RetirementAccountCreate,
    )
from app.features.records.base_repository import BaseUserRecordRepository


class AssetRepository(BaseUserRecordRepository):

    """Asset queries on top of the shared user record queries."""

    async def add_bank_account(self, user_id: int, account: BankAccountCreate) -> BankAccount:

        """Insert a bank account for the user."""

        return await self.insert(BankAccount, user_id, account.model_dump())

    async def add_fixed_deposit(self, user_id: int, deposit: FixedDepositCreate) -> FixedDeposit:

        """Insert a fixed or recurring deposit for the user."""

        return await self.insert(FixedDeposit, user_id, deposit.model_dump())

    async def add_retirement_account(self, user_id: int, account: RetirementAccountCreate) -> RetirementAccount:

        """Insert a retirement account for the user."""

        return await self.insert(RetirementAccount, user_id, account.model_dump())

    async def add_physical_asset(self, user_id: int, asset: PhysicalAssetCreate) -> PhysicalAsset:

        """Insert a physical asset for the user."""

        return await self.insert(PhysicalAsset, user_id, asset.model_dump())
