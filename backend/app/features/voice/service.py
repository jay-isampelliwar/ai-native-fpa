"""Turn one short recording into text with OpenAI's speech-to-text model, writing Hindi in English letters."""

import logging
from functools import lru_cache

from openai import APIError, APITimeoutError, AsyncOpenAI

from app.core.config import get_settings


log = logging.getLogger(__name__)

PROMPT = (
    "A person in India talks about their money: savings, SIPs, mutual funds, stocks, loans and goals. "
    "They may speak English, Hindi or a mix of both. Write every word in English letters, never in Devanagari. "
    "Write amounts as digits. Example: mera SIP 5000 ka hai, HDFC Flexi Cap mein 50,000 lagaye hain."
    )


class TranscriptionFailed(Exception):

    """The speech-to-text call did not give back text."""


class TranscriptionTimedOut(TranscriptionFailed):

    """The speech-to-text call took too long."""


@lru_cache
def client() -> AsyncOpenAI:

    """One OpenAI client for every transcription, built once."""

    settings = get_settings()

    return AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY.get_secret_value(),
        timeout=settings.TRANSCRIBE_TIMEOUT_SECONDS,
        max_retries=1,
        )


async def transcribe(
    audio: bytes,
    filename: str,
    content_type: str,
    ) -> str:

    """Send the recording to the speech-to-text model and return its text, trimmed."""

    try:
        result = await client().audio.transcriptions.create(
            model=get_settings().TRANSCRIBE_MODEL,
            file=(filename, audio, content_type),
            prompt=PROMPT,
            )

    except APITimeoutError as exc:
        raise TranscriptionTimedOut() from exc

    except APIError as exc:

        log.warning("transcription failed: %s", exc)

        raise TranscriptionFailed() from exc

    return result.text.strip()
