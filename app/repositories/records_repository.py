"""Writes to the user's financial records, used by the form path rather than by any skill.

This is the only module in the backend that inserts or updates a user's money records, and
no skill imports it. Data enters through validated endpoints a person filled in; the
conversation reads. When Phase 5 lets an approved proposal write, it will call these same
methods behind the approval gate rather than growing a second write path.

Identifiers are generated here with a per type prefix - ``inc_``, ``txn_``, ``sip_`` - and
returned to the caller. Those strings are the primary keys and they are also the
``evidence_ids`` a skill quotes, so a record's identity is the same string everywhere it
appears, from the database row to the sentence a user reads.

Nothing is ever deleted. ``archive`` sets ``active`` false, because a stopped SIP or a
closed loan is still the explanation for last year's numbers, and an audit trail that
points at a row that no longer exists explains nothing. Reads already exclude inactive
records, so archiving removes a record from every calculation without removing it from
history.

Ownership is checked on update and archive, not assumed. Every method takes the acting
``user_id`` and matches on it in the WHERE clause, so passing another user's record id
changes nothing and reports that it changed nothing.

Callers supply the session. These methods stage changes and never commit, so creating a
record and writing its audit row can be one transaction decided by whoever opened the scope.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import Frequency, SipStatus
from app.models.orm.cashflow import ExpenseRecordRow, ExpenseTransactionRow, IncomeRecordRow
from app.models.finance import DepositKind, HoldingKind
from app.models.orm.credit import EmiRecordRow, LiabilityRow, SipRecordRow
from app.models.orm.investments import DepositRow, HoldingRow, RetirementAssetRow

PREFIXES = {
    IncomeRecordRow: "inc",
    ExpenseRecordRow: "exp",
    ExpenseTransactionRow: "txn",
    LiabilityRow: "liab",
    EmiRecordRow: "emi",
    SipRecordRow: "sip",
    DepositRow: "dep",
    HoldingRow: "hold",
    RetirementAssetRow: "ret",
}


def new_id(row_class: type) -> str:

    """Mint a prefixed identifier that doubles as the evidence id a skill will quote."""

    return f"{PREFIXES[row_class]}_{uuid4().hex[:12]}"


class RecordsRepository:

    """Creates, updates and archives one user's financial records, never deleting anything."""

    async def create_income(
        self,
        session: AsyncSession,
        user_id: int,
        label: str,
        amount: Decimal,
        frequency: Frequency = Frequency.MONTHLY,
        source: str = "salary",
        ) -> IncomeRecordRow:

        """Add one income arrangement at the frequency the user actually receives it."""

        row = IncomeRecordRow(
            id=new_id(IncomeRecordRow),
            user_id=user_id,
            label=label,
            amount=amount,
            frequency=frequency,
            source=source,
        )

        session.add(row)

        await session.flush()

        return row

    async def create_expense(
        self,
        session: AsyncSession,
        user_id: int,
        label: str,
        amount: Decimal,
        frequency: Frequency = Frequency.MONTHLY,
        category: str = "general",
        ) -> ExpenseRecordRow:

        """Add one recurring cost, distinct from the transactions that realise it."""

        row = ExpenseRecordRow(
            id=new_id(ExpenseRecordRow),
            user_id=user_id,
            label=label,
            amount=amount,
            frequency=frequency,
            category=category,
        )

        session.add(row)

        await session.flush()

        return row

    async def create_liability(
        self,
        session: AsyncSession,
        user_id: int,
        label: str,
        principal_outstanding: Decimal,
        interest_rate_percent: Decimal,
        tenure_months: int,
        lender: str = "",
        opened_on: date | None = None,
        ) -> LiabilityRow:

        """Add a debt, which must exist before the EMI that services it can be created."""

        row = LiabilityRow(
            id=new_id(LiabilityRow),
            user_id=user_id,
            label=label,
            lender=lender,
            principal_outstanding=principal_outstanding,
            interest_rate_percent=interest_rate_percent,
            tenure_months=tenure_months,
            opened_on=opened_on,
        )

        session.add(row)

        await session.flush()

        return row

    async def create_emi(
        self,
        session: AsyncSession,
        user_id: int,
        liability_id: str,
        label: str,
        amount: Decimal,
        interest_rate_percent: Decimal,
        remaining_months: int,
        ) -> EmiRecordRow | None:

        """Add the contractual payment servicing a liability this user actually owns."""

        owns = await session.scalar(
            select(LiabilityRow.id).where(
                LiabilityRow.id == liability_id,
                LiabilityRow.user_id == user_id,
            )
        )

        if owns is None:
            return None

        row = EmiRecordRow(
            id=new_id(EmiRecordRow),
            user_id=user_id,
            liability_id=liability_id,
            label=label,
            amount=amount,
            interest_rate_percent=interest_rate_percent,
            remaining_months=remaining_months,
        )

        session.add(row)

        await session.flush()

        return row

    async def create_sip(
        self,
        session: AsyncSession,
        user_id: int,
        scheme_name: str,
        amount: Decimal,
        frequency: Frequency = Frequency.MONTHLY,
        folio_id: str | None = None,
        next_debit_on: date | None = None,
        linked_goal_id: str | None = None,
        ) -> SipRecordRow:

        """Add a standing instruction into a scheme, which is an arrangement and not an asset."""

        row = SipRecordRow(
            id=new_id(SipRecordRow),
            user_id=user_id,
            scheme_name=scheme_name,
            folio_id=folio_id,
            amount=amount,
            frequency=frequency,
            next_debit_on=next_debit_on,
            status=SipStatus.ACTIVE,
            linked_goal_id=linked_goal_id,
        )

        session.add(row)

        await session.flush()

        return row

    async def create_transaction(
        self,
        session: AsyncSession,
        user_id: int,
        occurred_on: date,
        amount: Decimal,
        category: str,
        merchant: str = "",
        description: str = "",
        import_batch_id: str | None = None,
        ) -> ExpenseTransactionRow:

        """Add one dated spend, tagging it with its import batch when it came from a statement."""

        row = ExpenseTransactionRow(
            id=new_id(ExpenseTransactionRow),
            user_id=user_id,
            occurred_on=occurred_on,
            amount=amount,
            category=category.lower(),
            merchant=merchant,
            description=description,
            import_batch_id=import_batch_id,
        )

        session.add(row)

        await session.flush()

        return row

    async def create_deposit(
        self,
        session: AsyncSession,
        user_id: int,
        kind: DepositKind,
        institution: str,
        interest_rate_percent: Decimal,
        opened_on: date,
        matures_on: date,
        principal: Decimal | None = None,
        monthly_contribution: Decimal | None = None,
        compounding: str = "quarterly",
        ) -> DepositRow:

        """Add a term or recurring deposit, whose kind decides which amount column is required."""

        row = DepositRow(
            id=new_id(DepositRow),
            user_id=user_id,
            kind=kind,
            institution=institution,
            principal=principal,
            monthly_contribution=monthly_contribution,
            interest_rate_percent=interest_rate_percent,
            compounding=compounding,
            opened_on=opened_on,
            matures_on=matures_on,
        )

        session.add(row)

        await session.flush()

        return row

    async def create_holding(
        self,
        session: AsyncSession,
        user_id: int,
        kind: HoldingKind,
        instrument_name: str,
        units: Decimal,
        average_cost: Decimal,
        as_of: date,
        isin: str | None = None,
        scheme_code: str | None = None,
        folio_id: str | None = None,
        asset_type: str | None = None,
        identifier_type: str = "symbol",
        invested_value: Decimal | None = None,
        current_value: Decimal | None = None,
        last_price: Decimal | None = None,
        source: str | None = None,
        account_label: str | None = None,
        import_batch_id: str | None = None,
        ) -> HoldingRow:

        """Add a position in one instrument, recording what a statement stated and what was computed from it."""

        row = HoldingRow(
            id=new_id(HoldingRow),
            user_id=user_id,
            kind=kind,
            instrument_name=instrument_name,
            isin=isin,
            scheme_code=scheme_code,
            folio_id=folio_id,
            units=units,
            average_cost=average_cost,
            as_of=as_of,
            asset_type=asset_type,
            identifier_type=identifier_type,
            invested_value=invested_value,
            current_value=current_value,
            last_price=last_price,
            source=source,
            account_label=account_label,
            import_batch_id=import_batch_id,
        )

        session.add(row)

        await session.flush()

        return row

    async def create_retirement_asset(
        self,
        session: AsyncSession,
        user_id: int,
        scheme: str,
        balance: Decimal,
        as_of: date,
        monthly_contribution: Decimal = Decimal("0"),
        employer_contribution: Decimal = Decimal("0"),
        interest_rate_percent: Decimal | None = None,
        account_reference: str | None = None,
        ) -> RetirementAssetRow:

        """Add an accumulation scheme such as EPF, PPF or NPS, with the balance as of a stated date."""

        row = RetirementAssetRow(
            id=new_id(RetirementAssetRow),
            user_id=user_id,
            scheme=scheme,
            account_reference=account_reference,
            balance=balance,
            monthly_contribution=monthly_contribution,
            employer_contribution=employer_contribution,
            interest_rate_percent=interest_rate_percent,
            as_of=as_of,
        )

        session.add(row)

        await session.flush()

        return row

    async def update_fields(
        self,
        session: AsyncSession,
        row_class: type,
        user_id: int,
        record_id: str,
        changes: dict,
        ) -> bool:

        """Apply changes to one record this user owns, reporting whether anything matched."""

        if not changes:
            return False

        result = await session.execute(
            update(row_class)
            .where(row_class.id == record_id, row_class.user_id == user_id)
            .values(**changes)
        )

        return result.rowcount > 0

    async def archive(
        self,
        session: AsyncSession,
        row_class: type,
        user_id: int,
        record_id: str,
        ) -> bool:

        """Retire a record from every future calculation while leaving it readable as history."""

        if row_class is SipRecordRow:
            return await self.update_fields(
                session,
                row_class,
                user_id,
                record_id,
                {"status": SipStatus.STOPPED},
            )

        return await self.update_fields(session, row_class, user_id, record_id, {"active": False})


records_repository = RecordsRepository()
