"""The table models for the user's own profile and their family members."""

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, Identity, Index, SmallInteger, String, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enums import FamilyRelation, RiskAppetite
from app.db.models.base import UserOwnedMixin, created_at_column, db_enum, updated_at_column
from app.db.session import Base


class User(Base):

    """One person who can sign in, with the profile details their plan is built on."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    city: Mapped[str | None] = mapped_column(String(100))
    risk_appetite: Mapped[RiskAppetite | None] = mapped_column(db_enum(RiskAppetite, "risk_appetite"))
    retirement_age: Mapped[int | None] = mapped_column(SmallInteger)
    life_expectancy: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="85")
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class FamilyMember(UserOwnedMixin, Base):

    """One person in the user's family, such as a spouse, child or parent."""

    __tablename__ = "family_members"

    __table_args__ = (
        Index("ix_family_members_user_id", "user_id"),
        )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    relation: Mapped[FamilyRelation] = mapped_column(db_enum(FamilyRelation, "family_relation"), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    is_dependent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
