"""Evaluating every alert rule for one user, from a single snapshot of their records.

Records are fetched once and handed to every rule. Seven rules each running their own queries would
be seven round trips for one screen, and worse, they could disagree - a rule reading income a
moment after another read expenses can produce a surplus figure that never existed.

Alerts are computed on request rather than stored. A stored alert goes stale the moment a record
changes, and a notification saying a goal is drifting after the user already fixed it is worse than
no notification. Delivery, when it arrives, should send what this returns rather than a queue of
findings from last week.

Results are ordered by severity and then by kind. What a person must decide about comes before what
is merely worth knowing, and a stable secondary order means a screen does not reshuffle between
refreshes for no reason.

Every alert carries evidence and, where a figure was computed, the calculator version behind it.
An unprompted claim about someone's money has to be traceable in the same way an answer they asked
for is - arguably more so, since they did not invite it.

The evaluation is read only. Nothing here writes a record, and no rule may: an alert is an
observation, and acting on it is the user's decision made through the ordinary approval path.
"""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.alerts.rules import MATURITY_WINDOW_DAYS, RULES, SEVERITY_ORDER, Alert, AlertContext
from app.calculations.cashflow.v1 import CashflowInput, run_cashflow
from app.core.config import settings
from app.db.session import session_scope
from app.models.orm.investments import DepositRow
from app.repositories import get_cashflow_repository
from app.repositories.goals_repository import goals_repository
from app.utils.dates import today_in_timezone


class AlertService:

    """Builds one snapshot of a user's position and runs every rule against it."""

    async def evaluate(self, user_id: int) -> list[Alert]:

        """Return every alert that fires for this user right now, most urgent first."""

        context = await self.build_context(user_id)

        alerts: list[Alert] = []

        for rule in RULES:
            alerts.extend(rule(context))

        return sorted(alerts, key=lambda alert: (SEVERITY_ORDER.get(alert.severity, 9), alert.kind))

    async def build_context(self, user_id: int) -> AlertContext:

        """Fetch everything the rules read, once, so no two rules can disagree about the same month."""

        as_of = today_in_timezone(settings.default_timezone)

        records = await get_cashflow_repository().get_cashflow_records(user_id)

        cashflow = run_cashflow(
            CashflowInput(
                income=[record.monthly_amount for record in records.income],
                expenses=[record.monthly_amount for record in records.expenses],
                emis=[record.monthly_amount for record in records.emis],
                sips=[record.monthly_amount for record in records.sips],
            )
        )

        goals = await goals_repository.list_snapshots(user_id)

        return AlertContext(
            as_of=as_of,
            records=records,
            cashflow=cashflow,
            goals=goals,
            maturing_deposits=await self.maturing_deposits(user_id, as_of),
        )

    async def maturing_deposits(self, user_id: int, as_of) -> list[dict]:

        """Find deposits maturing inside the warning window, which is money that moves without a decision."""

        horizon = as_of + timedelta(days=MATURITY_WINDOW_DAYS)

        async with session_scope() as session:

            rows = (
                await session.scalars(
                    select(DepositRow).where(
                        DepositRow.user_id == user_id,
                        DepositRow.active.is_(True),
                        DepositRow.matures_on >= as_of,
                        DepositRow.matures_on <= horizon,
                    )
                )
            ).all()

        return [
            {
                "id": row.id,
                "institution": row.institution,
                "matures_on": row.matures_on.isoformat(),
                "amount": str(row.principal or Decimal("0")),
            }
            for row in rows
        ]


alert_service = AlertService()
