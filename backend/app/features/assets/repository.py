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

    async def find_bank_account(self, user_id: int, account: BankAccountCreate) -> BankAccount | None:

        """Return the user's account at the same bank with the same type."""

        return await self.find_match(
            BankAccount,
            user_id,
            {"bank_name": account.bank_name, "account_type": account.account_type},
            )

    async def add_bank_account(self, user_id: int, account: BankAccountCreate) -> BankAccount:

        """Insert a bank account for the user."""

        return await self.insert(BankAccount, user_id, account.model_dump())

    async def add_fixed_deposit(self, user_id: int, deposit: FixedDepositCreate) -> FixedDeposit:

        """Insert a fixed or recurring deposit for the user."""

        return await self.insert(FixedDeposit, user_id, deposit.model_dump())

    async def find_retirement_account(
        self,
        user_id: int,
        account: RetirementAccountCreate,
        ) -> RetirementAccount | None:

        """Return the user's retirement account of the same type."""

        return await self.find_match(RetirementAccount, user_id, {"account_type": account.account_type})

    async def add_retirement_account(self, user_id: int, account: RetirementAccountCreate) -> RetirementAccount:

        """Insert a retirement account for the user."""

        return await self.insert(RetirementAccount, user_id, account.model_dump())

    async def find_physical_asset(self, user_id: int, asset: PhysicalAssetCreate) -> PhysicalAsset | None:

        """Return the user's physical asset with the same type and name."""

        return await self.find_match(PhysicalAsset, user_id, {"asset_type": asset.asset_type, "name": asset.name})

    async def add_physical_asset(self, user_id: int, asset: PhysicalAssetCreate) -> PhysicalAsset:

        """Insert a physical asset for the user."""

        return await self.insert(PhysicalAsset, user_id, asset.model_dump())
