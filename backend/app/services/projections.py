"""Goal projections computed in one place, so the panel and the conversation cannot disagree.

Two surfaces answer the same question about a goal. The workspace panel draws every goal as a
progress arc, and the ``goals_overview`` skill lists them when someone asks in the chat. Before this
module they would each have read the goals and each have called the calculator, which is two code
paths that are identical until the day one of them is edited - and the failure mode is the worst one
this product has, a figure on screen disagreeing with a figure in the answer beside it.

So the read and the projection happen here, once, and the two callers differ only in how they render
what comes back. ``run_goal_projection`` is still the only arithmetic; this adds the reading of the
rows and the ordering, which is what the two had duplicated.

The order is priority then target date, matching the panel's existing sort. It is the order a person
set, so the first goal in a list is the one they said matters most rather than the one that happens
to be nearest.

Nothing is cached. Every call reads the rows and re-runs the projection, which is what makes a
change to an SIP, a holding or a goal visible to the next question without anything being told to
recompute. A goal's funding is valued at read time inside the repository for the same reason.

``as_of`` is passed in rather than taken from the clock inside the loop, so every goal in one answer
is projected from the same day. A list where the first goal was projected on one date and the last on
the next is a difference nobody would ever spot and could not explain afterwards.
"""

from datetime import date

from pydantic import BaseModel

from app.calculations.goals.v1 import GoalInput, GoalProjection, run_goal_projection
from app.core.config import settings
from app.repositories.goals_repository import GoalSnapshot, goals_repository
from app.utils.dates import today_in_timezone


class ProjectedGoal(BaseModel):

    """One goal beside what the calculator concluded about it, which is what both surfaces render."""

    model_config = {"arbitrary_types_allowed": True}

    snapshot: GoalSnapshot
    projection: GoalProjection


def project_one(snapshot: GoalSnapshot, as_of: date) -> ProjectedGoal:

    """Run the versioned calculator over one goal's funding as it stands today."""

    projection = run_goal_projection(
        GoalInput(
            target_amount=snapshot.target_amount,
            target_date=snapshot.target_date,
            as_of=as_of,
            current_corpus=snapshot.funded_corpus,
            monthly_contribution=snapshot.monthly_contribution,
            inflation_percent=snapshot.inflation_percent,
        )
    )

    return ProjectedGoal(snapshot=snapshot, projection=projection)


async def projected_goals(user_id: int, as_of: date | None = None) -> list[ProjectedGoal]:

    """Read every active goal and project it, in the order the person's own priorities put them."""

    snapshots = await goals_repository.list_snapshots(user_id)

    if not snapshots:
        return []

    today = as_of or today_in_timezone(settings.default_timezone)

    ordered = sorted(snapshots, key=lambda goal: (goal.priority, goal.target_date))

    return [project_one(snapshot, today) for snapshot in ordered]


def evidence_from(goals: list[ProjectedGoal]) -> list[str]:

    """Collect every row behind a set of projections, keeping first appearance order and no repeats."""

    seen: dict[str, None] = {}

    for goal in goals:
        for identifier in goal.snapshot.evidence_ids:
            seen.setdefault(identifier, None)

    return list(seen)
