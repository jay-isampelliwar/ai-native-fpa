"""The runtime context: fixed facts about who is calling, passed in once per graph run."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PlannerContext:

    """Read-only data every node and tool can see during one run, set from the signed-in user."""

    user_id: int
