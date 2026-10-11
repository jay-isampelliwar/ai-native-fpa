"""Checked inputs for adding insurance policies."""

from datetime import date

from pydantic import BaseModel

from app.db.enums import PaymentFrequency, PolicyType
from app.features.records.schemas import Amount, Name, ShortName


class InsurancePolicyCreate(BaseModel):

    """One insurance policy to add, optionally for a named family member."""

    policy_type: PolicyType
    insurer: ShortName
    cover_amount: Amount
    premium: Amount
    premium_frequency: PaymentFrequency = PaymentFrequency.yearly
    policy_name: Name | None = None
    family_member_name: Name | None = None
    start_date: date | None = None
    renewal_date: date | None = None
    maturity_date: date | None = None
