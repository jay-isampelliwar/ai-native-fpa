"""Tests for the Langfuse setup with the client and handler faked, so no key or network is needed."""

from contextlib import nullcontext
from typing import Any

import pytest
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.observability import langfuse as observability
from app.features.runs.worker import TURN_SPAN_NAME, thread_config, traced_config
from app.observability.langfuse import (
    TRACE_NAME,
    TRACE_TAGS,
    create_langfuse,
    langfuse_enabled,
    langfuse_handler,
    shutdown_langfuse,
    start_langfuse,
    tracing_context,
    )


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


def fail(*args: Any, **kwargs: Any) -> Any:

    """Stand in for any Langfuse call that breaks, the way it would when Langfuse is down."""

    raise RuntimeError("langfuse is down")


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


def test_tracing_is_off_in_every_test() -> None:

    """The shared settings have no public key in tests, so no client, handler or trace attributes are made."""

    settings = get_settings()

    assert langfuse_enabled(settings) is False
    assert create_langfuse(settings) is None
    assert langfuse_handler(settings) is None
    assert isinstance(tracing_context(settings, 7, 42, 101, "host:1"), nullcontext)
    assert FakeLangfuse.built == []


def test_a_client_that_fails_to_start_is_logged_and_skipped(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    ) -> None:

    """A client that throws on start gives no client and no handler, and the error is logged."""

    monkeypatch.setattr(observability, "Langfuse", fail)

    assert create_langfuse(settings_with()) is None
    assert langfuse_handler(settings_with()) is None
    assert "Langfuse client failed to start" in caplog.text


def test_a_handler_that_fails_to_build_means_no_handler(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    ) -> None:

    """A handler that throws on build leaves the turn untraced, and the error is logged."""

    monkeypatch.setattr(observability, "CallbackHandler", fail)

    assert langfuse_handler(settings_with()) is None
    assert "callback handler failed to build" in caplog.text


def test_trace_attributes_carry_the_turn(monkeypatch: pytest.MonkeyPatch) -> None:

    """The turn's user, conversation as session, trace name, tags, run and worker reach Langfuse as strings."""

    given: list[dict[str, Any]] = []

    monkeypatch.setattr(observability, "propagate_attributes", lambda **kwargs: given.append(kwargs) or nullcontext())

    with tracing_context(settings_with(), 7, 42, 101, "host:1"):
        pass

    assert given == [
        {
            "user_id": "7",
            "session_id": "42",
            "trace_name": TRACE_NAME,
            "tags": TRACE_TAGS,
            "metadata": {"run_id": "101", "worker_id": "host:1"},
            },
        ]


def test_trace_attributes_that_fail_give_an_empty_context(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    ) -> None:

    """Trace attributes that throw give a context that does nothing, and the error is logged."""

    monkeypatch.setattr(observability, "propagate_attributes", fail)

    assert isinstance(tracing_context(settings_with(), 7, 42, 101, "host:1"), nullcontext)
    assert "trace attributes failed to build" in caplog.text


def test_a_failed_shutdown_is_logged_not_raised(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    ) -> None:

    """A shutdown that throws is logged, so the worker still closes Redis and the DB pool."""

    client = FakeLangfuse()
    client.shutdown = fail

    monkeypatch.setattr(observability, "create_langfuse", lambda settings: client)

    shutdown_langfuse(settings_with())

    assert "Langfuse shutdown failed" in caplog.text


def test_start_up_logs_that_tracing_is_on(caplog: pytest.LogCaptureFixture) -> None:

    """With keys, start-up builds the process's client and logs where traces go."""

    caplog.set_level("INFO", logger=observability.__name__)

    assert isinstance(start_langfuse(settings_with()), FakeLangfuse)
    assert f"Langfuse tracing is on, sending to {BASE_URL}" in caplog.text


def test_start_up_logs_that_tracing_is_off(caplog: pytest.LogCaptureFixture) -> None:

    """Without keys, start-up builds nothing and logs that tracing is off."""

    caplog.set_level("INFO", logger=observability.__name__)

    assert start_langfuse(settings_with(public_key=None)) is None
    assert "Langfuse tracing is off" in caplog.text


def test_the_turn_config_is_plain_when_tracing_is_off() -> None:

    """With tracing off, the graph gets the thread's own config and no callbacks."""

    assert traced_config(42) == thread_config(42)


def test_the_turn_config_carries_the_handler_when_tracing_is_on(monkeypatch: pytest.MonkeyPatch) -> None:

    """With tracing on, the graph gets the handler and the turn's root span name on top of the thread's config."""

    monkeypatch.setattr(get_settings(), "LANGFUSE_PUBLIC_KEY", PUBLIC_KEY)
    monkeypatch.setattr(get_settings(), "LANGFUSE_SECRET_KEY", SecretStr(SECRET_KEY))

    config = traced_config(42)

    assert config["configurable"] == {"thread_id": "42"}
    assert config["run_name"] == TURN_SPAN_NAME
    assert [type(handler) for handler in config["callbacks"]] == [FakeHandler]
