"""Date handling for a service whose users all live in one timezone but whose servers may not.

Every projection starts from "today", and a server running in UTC is already tomorrow for an
Indian user for five and a half hours of every day. A goal projected on the wrong side of that
boundary is off by a month at the margin, which changes a required contribution by a visible
amount and makes two runs of the same question disagree.

``today_in_timezone`` takes the zone explicitly rather than reading a global. Tests need to
pin a date, and a function that reaches for configuration cannot be pinned without patching
something unrelated.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo


def today_in_timezone(timezone: str) -> date:

    """Return the current date as the user experiences it, not as the server's clock reports it."""

    return datetime.now(ZoneInfo(timezone)).date()
