"""The form tool: open an input form beside the chat, prefilled with what the agent already knows."""

from typing import Annotated, Any

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage

from app.agent.blocks import form_block
from app.agent.context import PlannerContext
from app.agent.forms import FORM_FIELDS, FORM_TITLES, FormKind, known_values
from app.agent.tools.results import ok, to_message


FIELD_HELP = "; ".join(f"{kind.value}: {', '.join(fields)}" for kind, fields in FORM_FIELDS.items())


@tool
async def open_form(
    runtime: ToolRuntime[PlannerContext],
    form: Annotated[FormKind, "Which form to open."],
    values: Annotated[
        dict[str, Any] | None,
        f"Values the user already gave, to fill in for them, by field name. Fields per form: {FIELD_HELP}. "
        "Money in rupees as plain numbers, dates as YYYY-MM-DD.",
        ] = None,
    record_id: Annotated[int | None, "The id of a saved item, from list_records, when the form changes it."] = None,
    ) -> ToolMessage:

    """Open a form beside the chat so the user can type several details at once: a goal, income, expense, stock or fund, loan or insurance policy. Use it when the user wants to add or change one of these and has not given all its details. Read-only: nothing is saved until the user sends the form."""

    filled = known_values(form, values)

    message = (
        f"The {FORM_TITLES[form].lower()} form is open beside the chat. Say that you opened it "
        "for them to fill in. Do not ask for the details in the chat, and do not call any other tool now."
        )

    result = ok(message, {"form": form.value, "values": filled}, form_block(form.value, filled, record_id))

    return to_message(result, runtime.tool_call_id)
