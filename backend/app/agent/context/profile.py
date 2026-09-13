"""The user details block of the prompt: who the turn is for, and the id every tool call needs."""

from app.agent.agent_config import USER_DETAILS_TOKENS_THRESHOLD
from app.agent.context.tokens import count_text
from app.agent.state import PlannerState
from app.agent.user_data import UserProfile

PROFILE_HEADING = "Who you are talking to:"

ID_INSTRUCTION = "Pass this user_id to every tool you call. It is the only id you may ever use."

NO_PROFILE = "No user id was given for this turn, so you cannot call any tool. Say so and stop."


def profile_lines(profile: UserProfile) -> list[str]:

    """Lay the profile out one fact per line, starting with the id and dropping anything unfilled."""

    facts = {
        "user_id": profile.user_id,
        "name": profile.name,
        "email": profile.email,
        "timezone": profile.timezone,
        "currency": profile.currency,
    }

    return [f"- {label}: {value}" for label, value in facts.items() if value]


def render_profile(state: PlannerState) -> str:

    """Turn the profile into the text of one system message, refusing tool calls when there is no id."""

    profile = state.get("profile") or fallback_profile(state)

    if profile is None:
        return f"{PROFILE_HEADING}\n\n{NO_PROFILE}"

    lines = profile_lines(profile)

    return trim_profile(f"{PROFILE_HEADING}\n" + "\n".join(lines) + f"\n\n{ID_INSTRUCTION}")


def fallback_profile(state: PlannerState) -> UserProfile | None:

    """Build a bare profile from the id the request supplied, for a turn that loaded no profile row."""

    user_id = state.get("user_id")

    if not user_id:
        return None

    return UserProfile(user_id=user_id)


def trim_profile(text: str) -> str:

    """Drop facts off the front until the block fits, keeping the heading and the id instruction."""

    lines = text.splitlines()

    while len(lines) > 2 and count_text("\n".join(lines)) > USER_DETAILS_TOKENS_THRESHOLD:
        lines.pop(2)

    return "\n".join(lines)
