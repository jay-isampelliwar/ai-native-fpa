"""Business rules for adding bank accounts, deposits, retirement accounts and physical assets."""

from app.db.models import BankAccount, FixedDeposit, PhysicalAsset, RetirementAccount
from app.features.assets.repository import AssetRepository
from app.features.assets.schemas import (
    BankAccountCreate,
    FixedDepositCreate,
    PhysicalAssetCreate,
    RetirementAccountCreate,
    )
from app.features.records.service import BaseRecordService


class AssetService(BaseRecordService[AssetRepository]):

    """The steps behind the asset tools for one session."""

    repository_class = AssetRepository

    async def add_bank_account(self, user_id: int, account: BankAccountCreate) -> BankAccount:

        """Add the bank account. Two accounts at the same bank are allowed."""

        record = await self.repo.add_bank_account(user_id, account)

        await self.mark_provided(user_id, "bank_accounts")

        return record

    async def add_fixed_deposit(self, user_id: int, deposit: FixedDepositCreate) -> FixedDeposit:

        """Add the deposit; repeats are allowed, since many deposits at one bank are normal."""

        record = await self.repo.add_fixed_deposit(user_id, deposit)

        await self.mark_provided(user_id, "fixed_deposits")

        return record

    async def add_retirement_account(self, user_id: int, account: RetirementAccountCreate) -> RetirementAccount:

        """Add the retirement account."""

        record = await self.repo.add_retirement_account(user_id, account)

        await self.mark_provided(user_id, "retirement_accounts")

        return record

    async def add_physical_asset(self, user_id: int, asset: PhysicalAssetCreate) -> PhysicalAsset:

        """Add the physical asset."""

        record = await self.repo.add_physical_asset(user_id, asset)

        await self.mark_provided(user_id, "physical_assets")

        return record
