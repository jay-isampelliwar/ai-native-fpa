"""Business rules for adding bank accounts, deposits, retirement accounts and physical assets."""

from app.db.models import BankAccount, FixedDeposit, PhysicalAsset, RetirementAccount
from app.features.assets.repository import AssetRepository
from app.features.assets.schemas import (
    BankAccountCreate,
    FixedDepositCreate,
    PhysicalAssetCreate,
    RetirementAccountCreate,
    )
from app.features.records.exceptions import RecordExists
from app.features.records.service import BaseRecordService


class AssetService(BaseRecordService[AssetRepository]):

    """The steps behind the asset tools for one session."""

    repository_class = AssetRepository

    async def add_bank_account(self, user_id: int, account: BankAccountCreate) -> BankAccount:

        """Add the account unless one at the same bank with the same type is already saved."""

        existing = await self.repo.find_bank_account(user_id, account)

        if existing is not None:
            raise RecordExists("bank account", existing.id)

        record = await self.repo.add_bank_account(user_id, account)

        await self.mark_provided(user_id, "bank_accounts")

        await self.session.commit()

        return record

    async def add_fixed_deposit(self, user_id: int, deposit: FixedDepositCreate) -> FixedDeposit:

        """Add the deposit; repeats are allowed, since many deposits at one bank are normal."""

        record = await self.repo.add_fixed_deposit(user_id, deposit)

        await self.mark_provided(user_id, "fixed_deposits")

        await self.session.commit()

        return record

    async def add_retirement_account(self, user_id: int, account: RetirementAccountCreate) -> RetirementAccount:

        """Add the account unless one of the same type is already saved."""

        existing = await self.repo.find_retirement_account(user_id, account)

        if existing is not None:
            raise RecordExists("retirement account", existing.id)

        record = await self.repo.add_retirement_account(user_id, account)

        await self.mark_provided(user_id, "retirement_accounts")

        await self.session.commit()

        return record

    async def add_physical_asset(self, user_id: int, asset: PhysicalAssetCreate) -> PhysicalAsset:

        """Add the asset unless one with the same type and name is already saved."""

        existing = await self.repo.find_physical_asset(user_id, asset)

        if existing is not None:
            raise RecordExists("physical asset", existing.id)

        record = await self.repo.add_physical_asset(user_id, asset)

        await self.mark_provided(user_id, "physical_assets")

        await self.session.commit()

        return record
