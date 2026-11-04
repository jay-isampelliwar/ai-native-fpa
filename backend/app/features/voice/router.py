"""The voice route: the chat mic sends a short recording and gets its text back."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.api.deps import get_current_user_id
from app.core.config import get_settings
from app.features.voice.service import TranscriptionFailed, TranscriptionTimedOut, transcribe


router = APIRouter(prefix="/voice", tags=["voice"])

AUDIO_TYPES = ("audio/", "video/webm", "video/mp4")

FALLBACK_NAMES = {"mp4": "speech.mp4", "ogg": "speech.ogg", "wav": "speech.wav", "mpeg": "speech.mp3"}


class TranscriptResponse(BaseModel):

    """The text heard in one recording, empty when nothing was said."""

    text: str


def file_name(content_type: str) -> str:

    """A file name whose ending matches the audio format, which the model uses to read it."""

    for marker, name in FALLBACK_NAMES.items():

        if marker in content_type:
            return name

    return "speech.webm"


@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
    ) -> TranscriptResponse:

    """Turn one recording from the chat mic into text; the audio is never saved."""

    content_type = (audio.content_type or "").split(";")[0].strip().lower()

    if not content_type.startswith(AUDIO_TYPES):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Send an audio recording")

    limit = get_settings().MAX_AUDIO_BYTES
    data = await audio.read(limit + 1)

    if len(data) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The recording is too long")

    if not data:
        return TranscriptResponse(text="")

    try:
        text = await transcribe(data, file_name(content_type), content_type)

    except TranscriptionTimedOut as exc:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "Speech to text took too long. Please try again") from exc

    except TranscriptionFailed as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not turn your voice into text. Please try again") from exc

    return TranscriptResponse(text=text)
