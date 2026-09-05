"""Structured logging with redaction applied before anything is written, not after.

Every log line this service emits passes through ``redact_sensitive``. That processor
runs early in the chain, so a field named ``pan`` or ``account_number`` is replaced
before the renderer ever sees it - redaction that happens at the log aggregator instead
is redaction that has already failed, because the raw value crossed the network to get
there.

Redaction works on key names rather than on value patterns. Pattern matching for a PAN or
an account number in free text is unreliable in both directions: it misses formats it was
not written for and mangles ordinary values that happen to look similar. Naming the keys
that must never be logged is a smaller, checkable rule, and the cost is that a new
sensitive field has to be added to ``SENSITIVE_KEYS`` when it is introduced.

Amounts are not redacted. A surplus figure in a log is what makes an incident
reconstructable, and the audit trail already records the same numbers. What must never
appear is anything that identifies an account, a card, a credential or the free text of a
bank statement narrative, which is also the most likely carrier of prompt injection.

Logs are rendered as JSON in every environment except development, where a human is
reading them at a terminal. ``correlation_id`` is bound once per request and appears on
every line after that, so one user's complaint can be pulled out of a day of traffic
without searching on anything sensitive.
"""

import logging
import sys
from typing import Any

import structlog

from app.core.config import settings

SENSITIVE_KEYS = frozenset(
    {
        "account_number",
        "api_key",
        "authorization",
        "card_number",
        "cvv",
        "database_url",
        "encryption_key",
        "folio_id",
        "ifsc",
        "narrative",
        "otp",
        "pan",
        "password",
        "raw_statement",
        "secret",
        "token",
    }
)

REDACTED = "[redacted]"


def redact_sensitive(
    logger: Any,
    method_name: str,
    event_dict: dict,
    ) -> dict:

    """Replace every value whose key is known to be sensitive, before the line is rendered."""

    for key in list(event_dict):

        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = REDACTED

    return event_dict


def configure_logging() -> None:

    """Install the processor chain once at startup, rendering JSON outside development."""

    renderer = (
        structlog.dev.ConsoleRenderer()
        if settings.environment == "development"
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            redact_sensitive,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if settings.debug else logging.INFO
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def bind_request(correlation_id: str, user_id: int) -> None:

    """Attach the identifiers every later log line in this request should carry."""

    structlog.contextvars.clear_contextvars()

    structlog.contextvars.bind_contextvars(correlation_id=correlation_id, user_id=user_id)


def get_logger(name: str):

    """Return a bound logger for one module, sharing the configured processor chain."""

    return structlog.get_logger(name)
