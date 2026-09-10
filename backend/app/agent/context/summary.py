"""The rolling memory of the older turns: one fact per line, oldest lines falling off the front."""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.agent.agent_config import CONVERSATION_SUMMARY_TOKENS_THRESHOLD
from app.agent.context.tokens import count_text
from app.agent.state import PlannerState

SUMMARY_INSTRUCTIONS = """You keep the running memory of a financial planning conversation.

You are given the memory so far and the turns about to be dropped from the thread. Write the memory
that replaces both. Keep what still matters: what the person asked for, what was decided, what was
changed in their records, what they said about themselves, and anything still unanswered.

Write one short fact per line, oldest first and newest last. Merge a line that repeats an older one.
Do not add a figure that is not in what you were given, and do not offer advice. Return the lines
only, with no heading and no numbering."""

SUMMARY_HEADING = "What happened earlier in this conversation:"

NO_SUMMARY = "Nothing has been summarised yet, so this is still the start of the conversation."

SUMMARY_MODEL_MAX_TOKENS = 1_200


def render_summary(state: PlannerState) -> str:

    """Turn the rolling memory into the text of one system message, saying plainly when it is empty."""

    summary = state.get("conversation_summary")

    if not summary:
        return f"{SUMMARY_HEADING}\n\n{NO_SUMMARY}"

    return f"{SUMMARY_HEADING}\n\n{summary}"


def roll_summary(summary: str) -> str:

    """Keep the memory a fixed size queue of lines, dropping the oldest until it fits its budget."""

    lines = [line.strip() for line in summary.splitlines() if line.strip()]

    while lines and count_text("\n".join(lines)) > CONVERSATION_SUMMARY_TOKENS_THRESHOLD:
        lines.pop(0)

    return "\n".join(lines)


def summary_request(summary: str, dropped: list[BaseMessage]) -> list[BaseMessage]:

    """Build the one model call that folds the turns being dropped into the memory so far."""

    transcript = "\n".join(f"{message.type}: {message.content}" for message in dropped)

    known = summary or "nothing yet"

    return [
        SystemMessage(content=SUMMARY_INSTRUCTIONS),
        HumanMessage(content=f"Memory so far:\n{known}\n\nTurns being dropped:\n{transcript}"),
    ]


async def rewrite_summary(summary: str, dropped: list[BaseMessage]) -> str:

    """Ask the cheap model for the replacement memory, keeping the old one if the call gives nothing back."""

    from app.services.llm_service import get_router_model

    model = get_router_model().bind(max_tokens=SUMMARY_MODEL_MAX_TOKENS)

    answer = await model.ainvoke(summary_request(summary, dropped))

    written = getattr(answer, "content", "")

    if not isinstance(written, str) or not written.strip():
        return summary

    return roll_summary(written)
