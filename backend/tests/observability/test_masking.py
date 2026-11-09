"""Tests for the masking hook, built on fake span snapshots so no key or network is needed."""

import json
from typing import Any

from langfuse.types import MaskOtelSpansParams, OtelSpanData, OtelSpanIdentifier

from app.features.memory.context import MEMORY_HEADING
from app.observability.masking import HIDDEN, INPUT, OUTPUT, TYPE, hide_text, mask_spans


def span(attributes: dict[str, Any]) -> tuple[OtelSpanIdentifier, OtelSpanData]:

    """One fake span snapshot with these attributes, keyed the way the hook receives it."""

    data = OtelSpanData(
        trace_id="t",
        span_id="s",
        parent_span_id=None,
        name="step",
        instrumentation_scope_name="langfuse",
        instrumentation_scope_version=None,
        attributes=attributes,
        resource_attributes={},
        )

    return OtelSpanIdentifier(trace_id="t", span_id="s"), data


def patch_for(attributes: dict[str, Any]) -> Any:

    """Run the hook on one span and return the patch it made, or None."""

    identifier, data = span(attributes)

    return mask_spans(params=MaskOtelSpansParams(spans={identifier: data})).span_patches.get(identifier)


def test_a_tool_span_loses_its_input_and_output() -> None:

    """A tool's arguments and result never leave, because they hold balances and holdings."""

    patch = patch_for({TYPE: "tool", INPUT: '{"kind": "fd"}', OUTPUT: '{"balance": 500000}'})

    assert set(patch.delete_attributes) == {INPUT, OUTPUT}


def test_saved_memories_become_a_count() -> None:

    """A memory list in a node's output is replaced by how many there were."""

    patch = patch_for({TYPE: "chain", OUTPUT: json.dumps({"memories": ["salary 1,20,000", "two kids"]})})

    assert json.loads(patch.set_attributes[OUTPUT]) == {"memories": f"2 memories {HIDDEN}"}


def test_the_memory_message_is_hidden() -> None:

    """The memory system message keeps its heading and loses its lines."""

    assert hide_text(f"{MEMORY_HEADING}\n- salary 1,20,000") == f"{MEMORY_HEADING}\n{HIDDEN}"


def test_the_profile_block_is_hidden_but_the_prompt_stays() -> None:

    """The profile lines go, while the rest of the system prompt is kept for debugging."""

    text = "You are Preeti.\nAbout the user (from your memory):\n- name: Asha\n- city: Pune\nToday's date is 2026-11-09."

    hidden = hide_text(text)

    assert "Asha" not in hidden
    assert "You are Preeti." in hidden
    assert "Today's date is 2026-11-09." in hidden


def test_ids_are_hidden_and_amounts_are_kept() -> None:

    """Email, PAN, Aadhaar, phone and account numbers go, while an amount like 12,00,000 stays."""

    hidden = hide_text("asha@mail.com ABCDE1234F 1234 5678 9012 9876543210 acct 123456789012345 invest 12,00,000")

    for secret in ("asha@mail.com", "ABCDE1234F", "1234 5678 9012", "9876543210", "123456789012345"):
        assert secret not in hidden

    assert "12,00,000" in hidden


def test_a_span_with_no_input_or_output_is_left_alone() -> None:

    """A span carrying neither gets no patch."""

    assert patch_for({TYPE: "chain"}) is None
