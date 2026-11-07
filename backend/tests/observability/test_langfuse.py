"""Tests for the Langfuse setup with the client and handler faked, so no key or network is needed."""

from typing import Any

import pytest
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.observability import langfuse as observability
from app.observability.langfuse import create_langfuse, langfuse_enabled, langfuse_handler, shutdown_langfuse


PUBLIC_KEY = "pk-lf-test"
SECRET_KEY = "sk-lf-test"
BASE_URL = "https://us.cloud.langfuse.com"


class FakeLangfuse:

    """Stands in for the Langfuse client, keeping what it was built with and whether it was shut down."""

    built: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:

        """Remember the arguments instead of starting a real client."""

        self.kwargs = kwargs
        self.stopped = False

        FakeLangfuse.built.append(kwargs)

    def shutdown(self) -> None:

        """Mark the client as stopped instead of sending anything."""

        self.stopped = True


class FakeHandler:

    """Stands in for the LangChain callback handler, keeping the public key it was given."""

    def __init__(self, public_key: str | None = None) -> None:

        """Remember the public key instead of linking to a real client."""

        self.public_key = public_key


def settings_with(
    public_key: str | None = PUBLIC_KEY,
    secret_key: str | None = SECRET_KEY,
    ) -> Settings:

    """The app settings with only the Langfuse keys changed, so the real .env keys never reach a test."""

    return get_settings().model_copy(
        update={
            "LANGFUSE_PUBLIC_KEY": public_key,
            "LANGFUSE_SECRET_KEY": SecretStr(secret_key) if secret_key else None,
            "LANGFUSE_BASE_URL": BASE_URL,
            },
        )


@pytest.fixture(autouse=True)
def fake_langfuse(monkeypatch: pytest.MonkeyPatch) -> None:

    """Swap in the fake client and handler for every test, starting with no client built."""

    monkeypatch.setattr(observability, "Langfuse", FakeLangfuse)
    monkeypatch.setattr(observability, "CallbackHandler", FakeHandler)

    FakeLangfuse.built.clear()


def test_tracing_is_on_when_both_keys_are_set() -> None:

    """With a public and a secret key set, tracing is on."""

    assert langfuse_enabled(settings_with()) is True


@pytest.mark.parametrize(
    ("public_key", "secret_key"),
    [(None, SECRET_KEY), (PUBLIC_KEY, None), (None, None), ("", SECRET_KEY)],
    )
def test_tracing_is_off_when_a_key_is_missing(
    public_key: str | None,
    secret_key: str | None,
    ) -> None:

    """A missing or empty key turns tracing off."""

    assert langfuse_enabled(settings_with(public_key, secret_key)) is False


def test_no_client_is_built_without_keys() -> None:

    """Without keys no client is built, so the SDK never starts."""

    assert create_langfuse(settings_with(public_key=None)) is None
    assert FakeLangfuse.built == []


def test_the_client_gets_the_keys_and_base_url_with_the_secret_unwrapped() -> None:

    """The client is built with both keys and the base URL, the secret as plain text."""

    client = create_langfuse(settings_with())

    assert isinstance(client, FakeLangfuse)
    assert client.kwargs == {"public_key": PUBLIC_KEY, "secret_key": SECRET_KEY, "base_url": BASE_URL}


def test_no_handler_without_keys() -> None:

    """Without keys there is no handler, so LangChain gets no callback."""

    assert langfuse_handler(settings_with(secret_key=None)) is None
    assert FakeLangfuse.built == []


def test_the_handler_is_linked_to_the_client_by_public_key() -> None:

    """The handler is given the public key, after the client is built once."""

    handler = langfuse_handler(settings_with())

    assert isinstance(handler, FakeHandler)
    assert handler.public_key == PUBLIC_KEY
    assert len(FakeLangfuse.built) == 1


def test_shutdown_stops_the_client(monkeypatch: pytest.MonkeyPatch) -> None:

    """Shutdown stops the client, so traces still queued are sent."""

    client = FakeLangfuse()

    monkeypatch.setattr(observability, "create_langfuse", lambda settings: client)

    shutdown_langfuse(settings_with())

    assert client.stopped is True


def test_shutdown_does_nothing_without_keys() -> None:

    """Shutdown without keys builds nothing and does nothing."""

    shutdown_langfuse(settings_with(public_key=None))

    assert FakeLangfuse.built == []
