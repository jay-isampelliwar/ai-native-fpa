"""The endpoint that returns what the planner noticed without being asked.

Alerts are computed on request, so this endpoint is the whole of Phase 4's surface. There is no
list of stored notifications to mark read, because a stored alert is a claim that was true when it
was written and may not be now - and telling someone their goal is drifting after they fixed it
costs more trust than saying nothing.

The response carries evidence ids and calculator versions per alert, exactly as a planner answer
does. An unprompted claim about someone's money should be at least as traceable as one they asked
for.

Delivery is not here and should not be. When email or push arrives it sends what this returns; the
observation and the channel are different concerns, and merging them is how a notification system
ends up with its own copy of the rules.

There is no scheduler either. Running this on a cron is a deployment decision, and building one in
would make the alert logic untestable without waiting for a clock.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.alerts.rules import Alert
from app.alerts.service import alert_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertsResponse(BaseModel):

    """Everything the planner noticed for one user, ordered so what needs deciding comes first."""

    user_id: int
    total: int
    action_required: int
    alerts: list[Alert] = Field(default_factory=list)


@router.get("", response_model=AlertsResponse)
async def list_alerts(user_id: int) -> AlertsResponse:

    """Evaluate every rule against this user's current records and return what fired."""

    alerts = await alert_service.evaluate(user_id)

    return AlertsResponse(
        user_id=user_id,
        total=len(alerts),
        action_required=sum(1 for alert in alerts if alert.severity == "action"),
        alerts=alerts,
    )
