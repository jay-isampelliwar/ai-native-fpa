"""Request and response shapes for the record entry endpoints, where data actually enters.

These are deliberately strict. This is the surface a person types into, so validation here
is the last point at which a wrong number can be caught cheaply - once a salary is stored
as 15000 instead of 150000, every projection built on it is wrong and confidently so.

Amounts are ``Decimal`` with ``gt=0`` where a zero would be meaningless, and pydantic parses
JSON numbers into Decimal without going through float. That matters: a request body of
``150000.55`` must reach ``NUMERIC(14,2)`` unchanged, and a float round trip is exactly the
imprecision ``app.calculations.money`` exists to keep out.

Responses echo the generated ``id`` back. That string is the primary key, the evidence id a
skill will quote and the handle the client needs to edit or archive the record, so returning
it is not a convenience - without it the caller cannot refer to what they just created.

Update schemas make every field optional and are applied as a partial change. A form that
sends the whole object back would overwrite fields the user never touched with whatever the
client last read, which silently reverts a concurrent edit.

``user_id`` is in the request body because Phase 1 has no tokens, exactly as on the planner
endpoints. It moves to a verified credential later and nothing else here changes.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.finance import Frequency


class RecordCreated(BaseModel):

    """The identifier of a newly created record, which the client needs to edit or cite it."""

    id: str
    kind: str


class RecordChanged(BaseModel):

    """Whether a partial update or an archive matched a record this user owns."""

    id: str
    changed: bool


class IncomeCreate(BaseModel):

    """One income arrangement, recorded at the frequency the user actually receives it."""

    user_id: int
    label: str = Field(min_length=1, max_length=120)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    frequency: Frequency = Frequency.MONTHLY
    source: str = Field(default="salary", max_length=60)


class IncomeUpdate(BaseModel):

    """A partial change to an income arrangement, touching only the fields that were sent."""

    label: str | None = Field(default=None, min_length=1, max_length=120)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    frequency: Frequency | None = None
    source: str | None = Field(default=None, max_length=60)


class ExpenseCreate(BaseModel):

    """One recurring cost, distinct from the individual transactions that realise it."""

    user_id: int
    label: str = Field(min_length=1, max_length=120)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    frequency: Frequency = Frequency.MONTHLY
    category: str = Field(default="general", max_length=60)


class ExpenseUpdate(BaseModel):

    """A partial change to a recurring cost."""

    label: str | None = Field(default=None, min_length=1, max_length=120)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    frequency: Frequency | None = None
    category: str | None = Field(default=None, max_length=60)


class LiabilityCreate(BaseModel):

    """A debt, which must exist before an EMI can be attached to it."""

    user_id: int
    label: str = Field(min_length=1, max_length=120)
    lender: str = Field(default="", max_length=120)
    principal_outstanding: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    interest_rate_percent: Decimal = Field(ge=0, le=100, max_digits=6, decimal_places=3)
    tenure_months: int = Field(gt=0, le=600)
    opened_on: date | None = None


class EmiCreate(BaseModel):

    """The contractual payment servicing a liability the caller already owns."""

    user_id: int
    liability_id: str
    label: str = Field(min_length=1, max_length=120)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    interest_rate_percent: Decimal = Field(ge=0, le=100, max_digits=6, decimal_places=3)
    remaining_months: int = Field(ge=0, le=600)


class SipCreate(BaseModel):

    """A standing instruction into a scheme, adjustable later only through the approval path."""

    user_id: int
    scheme_name: str = Field(min_length=1, max_length=160)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    frequency: Frequency = Frequency.MONTHLY
    folio_id: str | None = Field(default=None, max_length=60)
    next_debit_on: date | None = None
    linked_goal_id: str | None = None


class TransactionCreate(BaseModel):

    """One dated spend, entered by hand or carried in by a statement import."""

    user_id: int
    occurred_on: date
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    category: str = Field(min_length=1, max_length=60)
    merchant: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=500)
    import_batch_id: str | None = None


class ArchiveRequest(BaseModel):

    """Retire a record from future calculations, identifying the owner making the request."""

    user_id: int
