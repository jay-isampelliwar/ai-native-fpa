"""Checking that a reply quotes only the figures the tools actually returned.

The model is told to quote figures rather than derive them. This is what makes that a rule rather than
a request. Every number in the reply is compared against the numbers in what the tools returned, and a
reply carrying one that was not there is set aside.

The sources are the raw tool results of this turn, taken from the agent's own message list rather than
plumbed through every tool. That matters more now than it did when skills returned finished sentences:
the model sees whole rows, so it has far more numbers in front of it and far more opportunity to add
two of them together. A total that no tool computed will not appear in any tool result, which is
exactly what this catches.

It is a check and not a gate, and the difference is worth stating. It cannot tell a correct sum from an
incorrect one - only that a number was not returned by anything - so it catches invention and would
miss a figure that happened to be quoted correctly from the wrong row.

A reply written in words rather than digits - "2.26 lakh" for 226,000 - is still set aside. Not
because it is wrong, but because a model that reformats a figure may reformat it wrongly, and there is
a correct sentence to fall back to.

Comparison is numeric rather than textual, and it has to be. Tools return money as it is stored -
"10000.00" - and a model quoting that writes "10,000", which as bare digit strings are "1000000" and
"10000" and share nothing. Stripping non digits was adequate while skills returned finished sentences
with figures already rendered; against raw rows it rejected almost every correct answer. So each match
is parsed as a number and canonicalised, which makes "10000.00", "10,000" and "10000" one value and
leaves a genuinely invented total with nothing to match.

Grouping, currency prefixes and trailing zeros therefore all wash out, and "1,00,000" - Indian
grouping, which a model will produce - normalises the same as "100000".

Numbers embedded in identifiers do not count as figures. A tool result carries ids like
``sip_3df758845eb1``, and reading digits out of those put "3", "758845" and "1" into the set of
figures a reply was allowed to quote - which did not break anything visible and quietly widened the
check until it would have permitted a small invented number. A figure has to stand on its own
between non alphanumeric characters to be one.

List ordinals are stripped from the reply before it is checked, and this is the one exclusion that is
about formatting rather than about arithmetic. A model answering "show my SIPs" writes a numbered
list, and the "2." at the head of the second line is not a claim about anybody's money - but it is a
number that appears in no tool result, so it set aside three otherwise perfect answers before this
existed. Only leading enumeration is removed, so a "2" inside a sentence is still a figure.

The person's own message counts as a source. Someone who says "I earn 1.5L" should be answered with
that figure repeated back, and it is theirs rather than one the planner claims to have computed.
"""

import re
from decimal import Decimal, InvalidOperation

NUMBER = re.compile(r"(?<![A-Za-z0-9_])\d[\d,]*(?:\.\d+)?(?![A-Za-z0-9_])")

ORDINAL = re.compile(r"^[ \t]*\d+[.)]\s", re.MULTILINE)


def canonical(raw: str) -> str | None:

    """Reduce one matched number to a single form, so how it was formatted cannot change what it is."""

    try:
        value = Decimal(raw.replace(",", ""))

    except InvalidOperation:
        return None

    normalised = value.normalize()

    return f"{normalised:f}"


def figures_in(text: str) -> set[str]:

    """Collect every number in a piece of text in canonical form, so formatting is not mistaken for fact."""

    found = set()

    for match in NUMBER.findall(text):

        value = canonical(match)

        if value is not None:
            found.add(value)

    return found


def without_ordinals(reply: str) -> str:

    """Drop leading list numbering, which is formatting rather than a claim about anybody's money."""

    return ORDINAL.sub("", reply)


def invents_figures(reply: str, sources: list[str]) -> bool:

    """Decide whether the reply quotes a number none of its sources contain."""

    allowed: set[str] = set()

    for source in sources:
        allowed |= figures_in(source)

    return not figures_in(without_ordinals(reply)).issubset(allowed)
