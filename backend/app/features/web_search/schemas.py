"""The freshness groups a search can belong to and the Tavily options each group searches with."""

from dataclasses import dataclass
from enum import StrEnum


class Freshness(StrEnum):

    """How fast the answer to a search goes stale, which decides how long its result is kept."""

    live = "live"
    today = "today"
    recent = "recent"
    evergreen = "evergreen"


@dataclass(frozen=True)
class SearchOptions:

    """Every Tavily option that can change a result, so each one is part of the cache key."""

    topic: str
    time_range: str | None
    country: str | None
    search_depth: str
    max_results: int


class WebSearchUnavailable(Exception):

    """Tavily could not be reached, timed out, refused the key, or no key is set."""
