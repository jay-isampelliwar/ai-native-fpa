"""The profile tools: save the user's own details and add their family members."""

from datetime import date
from typing import Annotated

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from pydantic import ValidationError

from app.agent.context import PlannerContext
from app.agent.tools.common import given_arguments, save_record
from app.agent.tools.records import show_value
from app.agent.tools.results import from_record_error, from_validation_error, ok, to_message
from app.db.enums import FamilyRelation, RiskAppetite
from app.db.session import SessionLocal
from app.features.profile.exceptions import ProfileError
from app.features.profile.schemas import FamilyMemberCreate, ProfileUpdate
from app.features.profile.service import ProfileService


@tool
async def update_profile(
    runtime: ToolRuntime[PlannerContext],
    name: Annotated[str | None, "The user's full name, only if they ask to change it."] = None,
    date_of_birth: Annotated[date | None, "The exact date of birth the user stated, as YYYY-MM-DD. Never work it out from an age."] = None,
    city: Annotated[str | None, "The city the user lives in."] = None,
    risk_appetite: Annotated[RiskAppetite | None, "How much investment risk the user accepts."] = None,
    retirement_age: Annotated[int | None, "The age the user wants to retire at, 40 to 80."] = None,
    life_expectancy: Annotated[int | None, "The age to plan until, greater than retirement age."] = None,
    ) -> ToolMessage:

    """Save the user's own profile details. Pass only the fields the user just told you. Email cannot be changed."""

    arguments = dict(locals())

    try:
        changes = ProfileUpdate(**given_arguments(arguments))

    except ValidationError as exc:
        return to_message(from_validation_error(exc), runtime.tool_call_id)

    try:

        async with SessionLocal() as session:
            saved = await ProfileService(session).update_profile(runtime.context.user_id, changes)

    except ProfileError as exc:
        return to_message(from_record_error(exc), runtime.tool_call_id)

    fields = {field: show_value(value) for field, value in saved.items()}

    return to_message(ok("Saved profile.", fields), runtime.tool_call_id)


@tool
async def add_family_member(
    runtime: ToolRuntime[PlannerContext],
    name: Annotated[str | None, "The person's real first name as the user said it. Never a relation word like Spouse or Kid."] = None,
    relation: Annotated[FamilyRelation | None, "How they are related to the user."] = None,
    date_of_birth: Annotated[date | None, "Their exact date of birth as YYYY-MM-DD, only if the user stated it."] = None,
    is_dependent: Annotated[bool | None, "True if they depend on the user for money."] = None,
    ) -> ToolMessage:

    """Add one person in the user's family. Needs their name and relation. If they already exist, you get their id back."""

    return await save_record(
        runtime,
        FamilyMemberCreate,
        dict(locals()),
        lambda session, user_id, member: ProfileService(session).add_family_member(user_id, member),
        "family member",
        )
