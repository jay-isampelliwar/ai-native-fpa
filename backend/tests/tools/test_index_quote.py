"""Tests for index quotes: reading Yahoo's daily bars, how long a quote is kept, the quote card, and the preview image reader."""

from datetime import datetime
from typing import Any

import pytest

from app.agent.blocks import quote_block
from app.core.config import get_settings
from app.features.indices.schemas import IndexName, QuoteUnavailable
from app.features.indices.service import IST, next_open, parse_chart, ttl_for
from app.features.web_search.preview import image_from_html, is_public


SESSION_START = int(datetime(2026, 11, 6, 9, 15, tzinfo=IST).timestamp())

SESSION_END = int(datetime(2026, 11, 6, 15, 30, tzinfo=IST).timestamp())


def chart(
    closes: list[float | None],
    price: float = 25030.35,
    stale_previous: float = 23960.6,
    ) -> dict[str, Any]:

    """A Yahoo chart body with one daily bar per close, whose own previousClose field is days old."""

    count = len(closes)

    return {
        "chart": {
            "result": [{
                "meta": {
                    "regularMarketPrice": price,
                    "previousClose": stale_previous,
                    "regularMarketTime": SESSION_END - 60,
                    "currentTradingPeriod": {"regular": {"start": SESSION_START, "end": SESSION_END}},
                    },
                "timestamp": list(range(count)),
                "indicators": {"quote": [{
                    "open": [24538.199921875] * count,
                    "high": [25030.349609375] * count,
                    "low": [24388.05078125] * count,
                    "close": closes,
                    }]},
                }],
            },
        }


def test_previous_close_comes_from_the_bar_before_the_last() -> None:

    """Yahoo's previousClose field is ignored; the close of the day before today is used, rounded to paise."""

    quote = parse_chart(IndexName.nifty_50, chart([23960.6, 24536.599609375, None]))

    assert quote.previous_close == 24536.6
    assert (quote.open, quote.high, quote.low) == (24538.2, 25030.35, 24388.05)
    assert quote.name == "NIFTY 50"


def test_broken_chart_is_unavailable() -> None:

    """A body with too few bars or missing fields raises a clean error, not a crash."""

    with pytest.raises(QuoteUnavailable):
        parse_chart(IndexName.sensex, chart([None]))

    with pytest.raises(QuoteUnavailable):
        parse_chart(IndexName.sensex, {"chart": {"result": []}})


def test_quote_is_kept_one_minute_while_open_and_until_next_open_when_closed() -> None:

    """Inside the session the TTL is one minute; on a Friday evening it lasts until Monday 9:15 am IST."""

    quote = parse_chart(IndexName.nifty_50, chart([24536.6, None]))

    during = datetime(2026, 11, 6, 11, 0, tzinfo=IST)
    friday_evening = datetime(2026, 11, 6, 18, 0, tzinfo=IST)

    assert ttl_for(quote, during) == get_settings().INDEX_QUOTE_OPEN_TTL_SECONDS
    assert next_open(friday_evening) == datetime(2026, 11, 9, 9, 15, tzinfo=IST)
    assert ttl_for(quote, friday_evening) == int((datetime(2026, 11, 9, 9, 15, tzinfo=IST) - friday_evening).total_seconds())


def test_one_index_gets_stats_and_many_do_not() -> None:

    """A single quote carries open, high, low and previous close; several carry only level and change."""

    up = parse_chart(IndexName.nifty_50, chart([24536.6, None]))
    down = parse_chart(IndexName.bank_nifty, chart([60000.0, None], price=59086.0))

    single = quote_block([up], False)

    assert single is not None and single["closed"] is True
    assert single["items"][0] | {"stats": None} == {
        "name": "NIFTY 50",
        "value": "25,030.35",
        "number": 25030.35,
        "change": "+493.75",
        "change_pct": "2.01%",
        "direction": "up",
        "stats": None,
        }
    assert [stat["label"] for stat in single["items"][0]["stats"]] == ["Open", "High", "Low", "Prev close"]

    many = quote_block([up, down], True)

    assert many is not None and many["closed"] is False
    assert all("stats" not in item for item in many["items"])
    assert many["items"][1]["direction"] == "down"
    assert many["items"][1]["change"] == "-914.00"


def test_image_from_html_prefers_og_image_and_makes_it_absolute() -> None:

    """og:image wins over twitter:image, a relative link is made full, and a page with none gives None."""

    html = (
        '<meta name="twitter:image" content="https://site.in/t.jpg">'
        '<meta content="/img/story.jpg?a=1&amp;b=2" property="og:image">'
        )

    assert image_from_html(html, "https://www.site.in/news/1") == "https://www.site.in/img/story.jpg?a=1&b=2"
    assert image_from_html("<html><head></head></html>", "https://site.in") is None
    assert image_from_html('<meta property="og:image" content="javascript:alert(1)">', "https://site.in") is None


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "file:///etc/passwd",
        ],
    )
async def test_private_and_local_addresses_are_never_opened(url: str) -> None:

    """Loopback, cloud metadata, private network and non-web links are refused before any request."""

    assert await is_public(url) is False
