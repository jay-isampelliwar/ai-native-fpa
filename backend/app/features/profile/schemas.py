"""Checked inputs for changing the user's profile and adding a family member."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.db.enums import FamilyRelation, RiskAppetite
from app.features.records.schemas import Name, PastDate, ShortName


PLACEHOLDER_NAMES = {
    "spouse",
    "wife",
    "husband",
    "child",
    "kid",
    "son",
    "daughter",
    "parent",
    "father",
    "mother",
    "sibling",
    "brother",
    "sister",
    "unknown",
    "not stated",
    "not given",
    "n/a",
    "na",
    "none",
    }


def real_member_name(value: str) -> str:

    """Refuse a relation word or a placeholder in place of the person's actual name."""

    if value.lower() in PLACEHOLDER_NAMES:
        raise ValueError(f"'{value}' is not a name. Ask the user for this person's real name")

    return value


class ProfileUpdate(BaseModel):

    """The profile fields the agent may change; email is left out on purpose."""

    name: Name | None = None
    date_of_birth: PastDate | None = None
    city: ShortName | None = None
    risk_appetite: RiskAppetite | None = None
    retirement_age: int | None = Field(default=None, ge=40, le=80)
    life_expectancy: int | None = Field(default=None, ge=41, le=110)


class FamilyMemberCreate(BaseModel):

    """One family member to add for the user."""

    name: Annotated[Name, AfterValidator(real_member_name)]
    relation: FamilyRelation
    date_of_birth: PastDate | None = None
    is_dependent: bool = False
