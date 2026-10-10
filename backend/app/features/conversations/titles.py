"""Turning a chat's first message into the short title the history list shows."""

TITLE_LENGTH = 80

DEFAULT_TITLE = "New chat"


def title_from(text: str | None) -> str:

    """Return the message's first line with spaces tidied, cut to TITLE_LENGTH with an ellipsis."""

    if not text or not text.strip():
        return DEFAULT_TITLE

    first_line = " ".join(text.strip().splitlines()[0].split())

    if len(first_line) <= TITLE_LENGTH:
        return first_line

    return first_line[: TITLE_LENGTH - 1].rstrip() + "…"
