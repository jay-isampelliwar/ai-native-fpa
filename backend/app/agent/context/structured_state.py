"""The records block of the prompt: what is loaded about the person's money, kept to its budget."""

import json

from app.agent.agent_config import STRUCTURED_STATE_TOKENS_THRESHOLD
from app.agent.context.tokens import count_text
from app.agent.state import PlannerState

RECORD_FIELDS = (
    "income",
    "expenses",
    "loans",
    "emis",
    "sips",
    "mutual_funds",
    "stocks",
    "deposits",
    "retirement_assets",
    "insurance_policies",
    "goals",
    "recent_spends",
)

CONTEXT_HEADING = "What is already known about this person's money, loaded before this turn:"

NOTHING_LOADED = "Nothing has been loaded yet. Call a tool before quoting any figure."


def get_structured_state(state: PlannerState) -> dict:

    """Collect the records this turn has loaded into one plain dict, leaving out what was never read."""

    context: dict = {}

    for field in RECORD_FIELDS:

        records = state.get(field)

        if records is None:
            continue

        context[field] = [record.model_dump(mode="json") for record in records]

    return context


def render_structured_state(state: PlannerState) -> str:

    """Turn the loaded records into the text of one system message, saying plainly when there are none."""

    context = get_structured_state(state)

    if not context:
        return f"{CONTEXT_HEADING}\n\n{NOTHING_LOADED}"

    return f"{CONTEXT_HEADING}\n\n{json.dumps(context, indent=2)}"


def render_queues(queues: dict) -> str:

    """Render what the records would look like after a trim, without writing anything back to state."""

    return render_structured_state(queues)


def trim_structured_state(state: PlannerState) -> dict:

    """Drop the oldest record off the longest list until the whole block fits its share of the budget."""

    if count_text(render_structured_state(state)) <= STRUCTURED_STATE_TOKENS_THRESHOLD:
        return {}

    queues = {field: list(state[field]) for field in RECORD_FIELDS if state.get(field)}

    trimmed: dict = {}

    while queues and count_text(render_queues(queues)) > STRUCTURED_STATE_TOKENS_THRESHOLD:

        longest = max(queues, key=lambda field: len(queues[field]))

        queues[longest].pop(0)

        trimmed[longest] = list(queues[longest])

        if not queues[longest]:
            queues.pop(longest)

    return trimmed
