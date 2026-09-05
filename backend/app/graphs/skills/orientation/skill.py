"""What the planner can do, and what it is still missing, answered from the registry rather than from a prompt.

Two questions had no home before this skill existed. "How can you help me?" and "what do you need
from me?" are not questions about money, so no financial skill fits them, and the router - told to
pick the closest skill when nothing fits - sent both to the cash flow summary, which refused them
identically because there were no records to summarise. A person new to the product therefore met a
refusal as their first and second answer, and neither told them what to do next.

The list of capabilities is read from the registry at answer time, not written into a string here.
A skill that is disabled stops being advertised the moment it stops being routable, which is the only
version of this that stays true: a hardcoded list would describe the product as it was when someone
last edited the paragraph.

What is missing is computed from the caller's own records rather than assumed. Someone who has
already imported holdings should not be told to import holdings, and the difference between "you have
given me nothing" and "you have given me everything except your EMIs" is the entire value of asking.

No model is called. Every sentence here is assembled from data the service already holds, so the
answer cannot describe a skill that is not registered or claim a record that is not there.

The result is deliberately ``answered`` with no evidence identifiers, which is legitimate only
because the definition sets ``quotes_figures`` to False. Nothing here is a conclusion about anyone's
money; it is a description of the service and a count of what it holds.
"""

from app.graphs.skills.contracts import SkillContext, SkillRequest, SkillResult
from app.graphs.skills.orientation.definition import DEFINITION
from app.graphs.skills.registry import registry
from app.repositories import get_cashflow_repository
from app.repositories.cashflow_repository import CashflowRepository
from app.ui.blocks import Block, CalloutBlock, TableBlock, TableColumn, TextBlock

WHAT_TO_SEND = {
    "income": "Your salary and any other income, with how often it arrives.",
    "expenses": "Your regular outgoings - rent, household, insurance premiums.",
    "emis": "Any loan repayments, with the lender and the amount.",
    "sips": "Your monthly investments, so they are not counted as spare cash.",
}


class OrientationSkill:

    """Describes what the planner can do and which of the caller's records are still missing."""

    name = DEFINITION.name
    version = DEFINITION.version

    def __init__(self, repository: CashflowRepository | None = None) -> None:

        """Take the repository to count records with, defaulting to the configured one."""

        self._repository = repository or get_cashflow_repository()

    async def execute(
        self,
        request: SkillRequest,
        context: SkillContext,
        ) -> SkillResult:

        """Report the registered capabilities and the record types this caller has not provided yet."""

        records = await self._repository.get_cashflow_records(context.user_id)

        held = {
            "income": len(records.income),
            "expenses": len(records.expenses),
            "emis": len(records.emis),
            "sips": len(records.sips),
        }

        missing = [name for name, count in held.items() if count == 0]

        return SkillResult(
            status="answered",
            message=self.summarise(held, missing),
            blocks=self.build_blocks(held, missing),
        )

    def summarise(self, held: dict[str, int], missing: list[str]) -> str:

        """Say what the planner does and what it still needs, in the plain text a client may render instead."""

        opening = "I read your own records and explain what they say about your money."

        if not missing:
            return f"{opening} I have everything I need, so ask me anything about your month."

        if len(missing) == len(held):
            return (
                f"{opening} I do not have any of your records yet - attach a statement below, or tell "
                "me your income and regular outgoings and I will start from there."
            )

        return f"{opening} I am still missing your {readable(missing)}."

    def build_blocks(self, held: dict[str, int], missing: list[str]) -> list[Block]:

        """Render the capabilities, what is held and what is needed as the blocks a client shows."""

        blocks: list[Block] = [TextBlock(text=self.capabilities())]

        blocks.append(
            TableBlock(
                title="What I have of yours",
                columns=[
                    TableColumn(key="record", label="Record", align="left"),
                    TableColumn(key="count", label="Held", align="right"),
                ],
                rows=[
                    {"record": label(name), "count": str(count) if count else "none yet"}
                    for name, count in held.items()
                ],
            )
        )

        if missing:
            blocks.append(
                CalloutBlock(
                    level="note",
                    text="To answer properly I still need: "
                    + " ".join(WHAT_TO_SEND[name] for name in missing)
                    + " You can attach a holdings or bank statement here and I will read it, and "
                    "nothing goes into your records until you accept it.",
                )
            )

        return blocks

    def capabilities(self) -> str:

        """List what the planner can currently answer, read from the registry so it cannot go stale."""

        lines = ["Here is what I can do today:"]

        for name in registry.routable_names():

            if name == DEFINITION.name:
                continue

            definition, _ = registry.resolve(name)

            lines.append(f"• {first_sentence(definition.description)}")

        return "\n".join(lines)


def first_sentence(description: str) -> str:

    """Take the leading sentence of a skill description, which is the part written for a reader."""

    head = description.split(". ")[0].strip()

    return head if head.endswith(".") else f"{head}."


def label(name: str) -> str:

    """Name one record type the way a person would say it rather than the way a table stores it."""

    return {"income": "Income", "expenses": "Regular expenses", "emis": "Loan EMIs", "sips": "SIPs"}[name]


def readable(names: list[str]) -> str:

    """Join the missing record types into the phrase a sentence can end on."""

    spoken = [label(name).lower() for name in names]

    if len(spoken) == 1:
        return spoken[0]

    return f"{', '.join(spoken[:-1])} and {spoken[-1]}"
