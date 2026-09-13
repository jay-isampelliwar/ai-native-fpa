"""Writing one staged record of whichever kind an import produced, in the shape the extractors emit.

This is the commit half of the document pipeline and nothing else uses it. An extractor stages rows
shaped ``{"kind": ..., "fields": {...}}`` because that is what a spreadsheet row naturally becomes; the
import service accepts or rejects them one by one; and this turns an accepted one into the right table.

It lived in the controlled write module while every write went through a human approval, which made it
sit beside the approval machinery it had nothing to do with - an imported row is confirmed on the
reconciliation screen, not on an approval card. When the approval layer was removed with the skills,
this was the one function in it that was still needed, so it moved here beside the service that calls
it.

An EMI creates its liability first, because the database refuses an EMI whose loan does not exist and
is right to: a repayment with nothing to repay breaks every projection that reads it. Where the sheet
did not state a principal, the remaining payments stand in for one - which is an understatement rather
than a guess, and is visible as such next to a stated interest rate of zero.

An unknown kind returns None rather than raising. The caller counts what was written and skips what it
could not place, so one unrecognised row does not abort a statement that was otherwise readable.
"""

from decimal import Decimal

from app.models.finance import Frequency
from app.repositories.records_repository import records_repository


async def write_one(session, user_id: int, record: dict):

    """Create one record of whichever kind was confirmed, returning None for a kind nothing handles."""

    kind = record.get("kind")

    fields = record.get("fields") or {}

    amount = Decimal(str(fields["amount"]))

    frequency = Frequency(fields.get("frequency", "monthly"))

    if kind == "income":
        return await records_repository.create_income(
            session,
            user_id=user_id,
            label=fields["label"],
            amount=amount,
            frequency=frequency,
            source=fields.get("source", "salary"),
        )

    if kind == "expense":
        return await records_repository.create_expense(
            session,
            user_id=user_id,
            label=fields["label"],
            amount=amount,
            frequency=frequency,
            category=fields.get("category", "general"),
        )

    if kind == "emi":

        months = int(fields.get("remaining_months") or 0)

        rate = Decimal(str(fields.get("interest_rate_percent") or "0"))

        liability = await records_repository.create_liability(
            session,
            user_id=user_id,
            label=fields["label"],
            principal_outstanding=Decimal(str(fields.get("principal_outstanding") or amount * months)),
            interest_rate_percent=rate,
            tenure_months=months,
            lender=fields.get("lender") or "",
        )

        return await records_repository.create_emi(
            session,
            user_id=user_id,
            liability_id=liability.id,
            label=fields["label"],
            amount=amount,
            interest_rate_percent=rate,
            remaining_months=months,
        )

    if kind == "sip":
        return await records_repository.create_sip(
            session,
            user_id=user_id,
            scheme_name=fields["label"],
            amount=amount,
            frequency=frequency,
        )

    return None
