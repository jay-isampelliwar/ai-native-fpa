"""Turn one short recording into text with OpenAI's speech-to-text model, writing Hindi in English letters."""

import logging
import re
from functools import lru_cache

from openai import APIError, APITimeoutError, AsyncOpenAI

from app.core.config import get_settings


log = logging.getLogger(__name__)

PROMPT = "Personal finance talk in English, Hindi or Hinglish. Use English letters only, never Devanagari. Write amounts as digits."

ECHO_WORDS = 4


def words_of(text: str) -> list[str]:

    """The lowercase words of a text, without punctuation."""

    return re.findall(r"[a-z0-9]+", text.lower())


def word_runs(words: list[str]) -> set[tuple[str, ...]]:

    """Every run of ECHO_WORDS words in a row."""

    return {tuple(words[index:index + ECHO_WORDS]) for index in range(len(words) - ECHO_WORDS + 1)}


PROMPT_RUNS = word_runs(words_of(PROMPT))


def repeats_prompt(text: str) -> bool:

    """True when the model gave back part of its own instructions, which it can do on a short or silent clip."""

    return bool(word_runs(words_of(text)) & PROMPT_RUNS)


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

    text = result.text.strip()

    if repeats_prompt(text):

        log.info("dropped a transcript that repeated the instructions")

        return ""

    return text
