"""The tables a cash flow question reads: what arrives, what leaves, and what was actually spent.

``IncomeRecordRow`` and ``ExpenseRecordRow`` describe recurring arrangements at their
natural frequency. A salary is monthly and an insurance premium is annual, and both are
stored the way the user knows them rather than pre-divided, because a stored monthly
equivalent is a derived value that goes stale the moment the real amount changes.

``ExpenseTransactionRow`` is a different thing entirely and is kept separate for that
reason. A recurring expense is an arrangement; a transaction is one dated event. Spending
investigations read transactions, cash flow summaries read arrangements, and collapsing
them would make the second answer wrong every time a month's actual spending differed from
its budget.

``description`` on a transaction is untrusted text. It arrives from a bank or a merchant
through a statement import, and the seeded data contains a real example of one carrying an
instruction aimed at a model. Nothing in the database can defend against that; what defends
against it is that the tools exposing this column cannot write and are labelled as
untrusted where the model reads them.

``import_batch_id`` tags every row that arrived in one upload, so a bad statement import
can be identified and reversed as a unit instead of row by row.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Money, RecordId, TimestampMixin
from app.models.finance import Frequency
from app.models.orm.enums import FREQUENCY


class IncomeRecordRow(Base, TimestampMixin):

    """Money arriving on a schedule, stored at the frequency the user actually receives it."""

    __tablename__ = "income_records"

    id: Mapped[RecordId]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Money]
    frequency: Mapped[Frequency] = mapped_column(FREQUENCY, nullable=False, default=Frequency.MONTHLY)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="salary")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ExpenseRecordRow(Base, TimestampMixin):

    """A recurring cost, distinct from the individual transactions that realise it."""

    __tablename__ = "expense_records"

    id: Mapped[RecordId]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Money]
    frequency: Mapped[Frequency] = mapped_column(FREQUENCY, nullable=False, default=Frequency.MONTHLY)
    category: Mapped[str] = mapped_column(Text, nullable=False, default="general")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ExpenseTransactionRow(Base):

    """One dated spend, the unit a spending investigation reads."""

    __tablename__ = "expense_transactions"
    __table_args__ = (
        Index("ix_expense_transactions_user_date", "user_id", "occurred_on"),
        Index("ix_expense_transactions_user_category_date", "user_id", "category", "occurred_on"),
    )

    id: Mapped[RecordId]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Money]
    category: Mapped[str] = mapped_column(Text, nullable=False)
    merchant: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    import_batch_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
