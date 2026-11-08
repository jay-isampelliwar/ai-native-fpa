"""Hide personal data in every span before it leaves for Langfuse: tool inputs and outputs, saved memories, the profile block and ID-like numbers."""

import json
import logging
import re
from typing import Any

from langfuse import LangfuseOtelSpanAttributes
from langfuse.types import MaskOtelSpansParams, MaskOtelSpansResult, OtelSpanData, OtelSpanPatch

from app.features.memory.context import MEMORY_HEADING


log = logging.getLogger(__name__)

INPUT = LangfuseOtelSpanAttributes.OBSERVATION_INPUT
OUTPUT = LangfuseOtelSpanAttributes.OBSERVATION_OUTPUT
TYPE = LangfuseOtelSpanAttributes.OBSERVATION_TYPE

HIDDEN = "[hidden]"
TOOL_TYPE = "tool"
MEMORIES_KEY = "memories"
PROFILE_BLOCK = re.compile(r"About the user \(from your memory\):\n(?:- .*(?:\n|$))+")

PERSONAL_PATTERNS = (
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b"),
    re.compile(r"(?:\+91[ -]?)?\b[6-9]\d{9}\b"),
    re.compile(r"\b\d{9,18}\b"),
    )


def hide_text(text: str) -> str:

    """Hide the memory message, the profile block, and emails, PAN, Aadhaar, phone and account numbers in one piece of text."""

    if text.startswith(MEMORY_HEADING):
        return f"{MEMORY_HEADING}\n{HIDDEN}"

    text = PROFILE_BLOCK.sub(f"About the user: {HIDDEN}\n", text)

    for pattern in PERSONAL_PATTERNS:
        text = pattern.sub(HIDDEN, text)

    return text


def hide_value(value: Any) -> Any:

    """Walk a decoded input or output, hiding text everywhere and every saved memory list down to its count."""

    if isinstance(value, str):
        return hide_text(value)

    if isinstance(value, list):
        return [hide_value(item) for item in value]

    if not isinstance(value, dict):
        return value

    return {
        key: f"{len(item)} memories {HIDDEN}" if key == MEMORIES_KEY and isinstance(item, list) else hide_value(item)
        for key, item in value.items()
        }


def hide_attribute(raw: str) -> str:

    """Hide personal data in one input or output attribute, decoding it as JSON when it is JSON."""

    try:
        decoded = json.loads(raw)

    except ValueError:
        return hide_text(raw)

    return json.dumps(hide_value(decoded), ensure_ascii=False)


def span_patch(span: OtelSpanData) -> OtelSpanPatch | None:

    """Drop a tool's input and output whole, hide personal data in any other span's, or None when the span carries neither."""

    present = [key for key in (INPUT, OUTPUT) if isinstance(span.attributes.get(key), str)]

    if not present:
        return None

    if span.attributes.get(TYPE) == TOOL_TYPE:
        return OtelSpanPatch(delete_attributes=present)

    return OtelSpanPatch(set_attributes={key: hide_attribute(span.attributes[key]) for key in present})


def mask_spans(*, params: MaskOtelSpansParams) -> MaskOtelSpansResult:

    """Patch every span in one export batch, dropping a span's input and output whole if hiding them fails, so nothing leaks."""

    patches: dict[Any, OtelSpanPatch] = {}

    for identifier, span in params.spans.items():

        try:
            patch = span_patch(span)

        except Exception:

            log.exception("Langfuse masking failed on span %s, so its input and output are dropped", span.name)

            patch = OtelSpanPatch(delete_attributes=(INPUT, OUTPUT))

        if patch is not None:
            patches[identifier] = patch

    return MaskOtelSpansResult(span_patches=patches)
