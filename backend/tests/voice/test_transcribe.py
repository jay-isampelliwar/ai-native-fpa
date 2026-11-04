"""Tests for the voice route with the speech-to-text call faked, so no OpenAI key or network is needed."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.auth.security import SESSION_COOKIE, create_token
from app.features.voice import router as voice_router
from app.features.voice.service import TranscriptionFailed, TranscriptionTimedOut


heard: list[tuple[bytes, str, str]] = []


def make_client(signed_in: bool = True) -> TestClient:

    """A client for an app with only the voice route, signed in as user 7 unless told otherwise."""

    app = FastAPI()
    app.include_router(voice_router.router, prefix="/api")

    client = TestClient(app)

    if signed_in:
        client.cookies.set(SESSION_COOKIE, create_token(7))

    return client


def send(
    client: TestClient,
    body: bytes = b"voice",
    content_type: str = "audio/webm;codecs=opus",
    ):

    """Post one recording the way the browser does."""

    return client.post("/api/voice/transcribe", files={"audio": ("blob", body, content_type)})


@pytest.fixture(autouse=True)
def fake_model(monkeypatch: pytest.MonkeyPatch) -> None:

    """Answer every transcription with fixed Hinglish text, and remember what was sent."""

    async def transcribe(audio: bytes, filename: str, content_type: str) -> str:

        """Pretend to hear the recording."""

        heard.append((audio, filename, content_type))

        return "mera SIP 5000 ka hai"

    monkeypatch.setattr(voice_router, "transcribe", transcribe)

    heard.clear()


def test_a_recording_comes_back_as_text() -> None:

    """A signed-in user's recording is turned into text, with a file name the model can read."""

    response = send(make_client())

    assert response.status_code == 200
    assert response.json() == {"text": "mera SIP 5000 ka hai"}
    assert heard == [(b"voice", "speech.webm", "audio/webm")]


def test_safari_audio_keeps_its_format() -> None:

    """An mp4 recording from Safari is named mp4, so the model reads it as mp4."""

    send(make_client(), content_type="audio/mp4")

    assert heard[0][1] == "speech.mp4"


def test_signed_out_is_refused() -> None:

    """Without a session cookie, nothing is sent to the model."""

    response = send(make_client(signed_in=False))

    assert response.status_code == 401
    assert heard == []


def test_a_non_audio_file_is_refused() -> None:

    """A file that is not audio is refused before the model is called."""

    response = send(make_client(), content_type="application/pdf")

    assert response.status_code == 415
    assert heard == []


def test_a_too_long_recording_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:

    """A recording over the size limit is refused before the model is called."""

    monkeypatch.setattr(voice_router.get_settings(), "MAX_AUDIO_BYTES", 4)

    response = send(make_client(), body=b"12345")

    assert response.status_code == 413
    assert heard == []


def test_an_empty_recording_gives_empty_text() -> None:

    """An empty recording gives empty text without calling the model."""

    response = send(make_client(), body=b"")

    assert response.json() == {"text": ""}
    assert heard == []


@pytest.mark.parametrize(("error", "code"), [(TranscriptionTimedOut(), 504), (TranscriptionFailed(), 502)])
def test_a_model_failure_is_a_clear_error(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    code: int,
    ) -> None:

    """A slow or failed model call answers with a status and a message the user can read."""

    async def broken(audio: bytes, filename: str, content_type: str) -> str:

        """Fail like the model would."""

        raise error

    monkeypatch.setattr(voice_router, "transcribe", broken)

    response = send(make_client())

    assert response.status_code == code
    assert "try again" in response.json()["detail"]
