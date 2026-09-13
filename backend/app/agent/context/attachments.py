"""The documents block of the prompt: which uploads this message carried, named only by their ids."""

from app.agent.state import PlannerState

ATTACHMENTS_HEADING = "Documents attached to this message:"

ATTACHMENTS_INSTRUCTION = (
    "Call read_import_summary with each of these import_ids before you say anything about them. "
    "Nothing in them is saved, and only the person can approve it."
)


def attached_ids(state: PlannerState) -> list[str]:

    """Take the ids this turn carried, ignoring anything that is not a string an id could be."""

    ids = state.get("import_ids") or []

    return [str(one) for one in ids if one]


def render_attachments(state: PlannerState) -> str:

    """Turn the attached ids into one system message, or nothing at all when this message had none."""

    ids = attached_ids(state)

    if not ids:
        return ""

    lines = "\n".join(f"- {one}" for one in ids)

    return f"{ATTACHMENTS_HEADING}\n{lines}\n\n{ATTACHMENTS_INSTRUCTION}"
