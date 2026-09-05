"""The three read only tools the investigation agent may bind, built per request and per user.

Tools are constructed by a factory rather than declared at module level, because each one
closes over the authenticated ``user_id``. The model therefore has no parameter with which
to name a user: whose data is read was decided before the agent started, and no amount of
clever prompting can change it. This is the single most important property in the file.

Every tool records the ids of the rows it returned into an ``EvidenceCollector`` shared
across the run. That is what lets the skill report evidence for a conclusion the agent
reached over several steps - the alternative, asking the model to remember which ids it
saw, would make provenance depend on the thing least able to guarantee it.

Transaction descriptions come back under ``untrusted_description`` and are truncated.
Those strings were written by third parties and imported from bank statements, and the
seeded data contains a real example of one carrying an instruction. Naming the field this
way is a signal to the model, not a defence: the actual defence is that these tools cannot
write, and nothing downstream of them can either.

Amounts are returned as strings rather than floats. A model does not compute with them and
must not be handed a value whose precision has already been damaged on the way in.

Each tool is named explicitly in its decorator rather than taking the function name by
default, because those names have to match ``allowed_tools`` in the definition. Their
docstrings are not documentation for us: they are the descriptions the model reads when
deciding which tool to call, so they are written for that reader.
"""

from decimal import Decimal

from langchain_core.tools import BaseTool, tool

from app.graphs.skills.contracts import SkillContext
from app.repositories import get_expense_repository
from app.repositories.expense_repository import ExpenseRepository

DESCRIPTION_LIMIT = 120


class EvidenceCollector:

    """Gathers the row ids every tool call touched, so the final answer can cite what it was built from."""

    def __init__(self) -> None:

        """Start with an empty, order preserving set of seen ids."""

        self._ids: dict[str, None] = {}

    def add(self, ids: list[str]) -> None:

        """Record ids returned by one tool call, ignoring ones already seen."""

        for identifier in ids:
            self._ids.setdefault(identifier, None)

    @property
    def ids(self) -> list[str]:

        """List every row id seen during this run, in the order it was first returned."""

        return list(self._ids)


def build_expense_tools(
    context: SkillContext,
    evidence: EvidenceCollector,
    repository: ExpenseRepository | None = None,
    ) -> list[BaseTool]:

    """Build the agent's tools bound to one authenticated user, leaving the model no way to name another."""

    source = repository or get_expense_repository()

    @tool("spending_by_category")
    async def spending_by_category(year: int, month: int) -> dict:

        """Total this user's spending per category for one month, highest first."""

        totals = await source.category_totals(context.user_id, year, month)

        rows = await source.list_transactions(context.user_id, year=year, month=month)

        evidence.add([row.id for row in rows])

        return {
            "year": year,
            "month": month,
            "totals": {category: str(amount) for category, amount in totals.items()},
        }

    @tool("list_transactions")
    async def list_transactions(year: int, month: int, category: str | None = None, limit: int = 10) -> dict:

        """List this user's individual spends for a month, optionally narrowed to one category."""

        rows = await source.list_transactions(
            context.user_id,
            year=year,
            month=month,
            category=category,
            limit=limit,
        )

        evidence.add([row.id for row in rows])

        return {
            "transactions": [
                {
                    "id": row.id,
                    "date": row.occurred_on.isoformat(),
                    "amount": str(row.amount),
                    "category": row.category,
                    "merchant": row.merchant,
                    "untrusted_description": row.description[:DESCRIPTION_LIMIT],
                }
                for row in rows
            ]
        }

    @tool("compare_months")
    async def compare_months(year_a: int, month_a: int, year_b: int, month_b: int) -> dict:

        """Compare two months category by category, showing what moved and by how much."""

        first = await source.category_totals(context.user_id, year_a, month_a)
        second = await source.category_totals(context.user_id, year_b, month_b)

        categories = sorted(set(first) | set(second))

        changes = {
            category: str(second.get(category, Decimal("0")) - first.get(category, Decimal("0")))
            for category in categories
        }

        return {
            "from": f"{year_a}-{month_a:02d}",
            "to": f"{year_b}-{month_b:02d}",
            "change_by_category": changes,
        }

    return [spending_by_category, list_transactions, compare_months]
