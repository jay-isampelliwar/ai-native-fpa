"""What the planner still needs from a person, in one place, phrased as questions with working answers.

Two skills reach the same dead end from opposite directions. Orientation is asked "how can you help
me?" by someone whose records are empty, and the cash flow summary is asked "what is my income?" by
the same person a moment later. Both used to answer with prose about a gap - one listed four things
to send in a single run-on sentence, the other refused and named two of them - and neither gave the
person anything to act on beyond re-reading the sentence. The ask is built here so both use the same
words, and so adding a fifth record type does not mean finding every skill that mentions the other
four.

The order is by what unlocks the most, not by what the tables happen to list. Income first, because
no surplus figure exists without it; expenses second, because income alone reports a 100% savings
rate; then EMIs and SIPs, which move the same figure by smaller amounts. A person who answers only
the first question has still made the planner useful, which is the property this order is chosen for.

The examples are real answers, not illustrations. Each one is a sentence ``record_capture`` already
parses, so a client can offer them as something to send rather than as a format to imitate - and a
person who taps one gets a proposal card back, which is the whole loop working on their first
message. The EMI examples all state a tenure because the capture skill refuses a liability without
one; an example that would be rejected teaches the wrong sentence.

Nothing here reads a record or quotes a figure. The caller passes in the counts it already fetched,
so this module cannot disagree with the table rendered beside its output.
"""

from typing import NamedTuple

from app.ui.blocks import PromptBlock, PromptItem

ATTACH_NOTE = (
    "You can also attach a bank or holdings statement and I will read it. Nothing goes into your "
    "records until you accept it."
)


class Ask(NamedTuple):

    """One record type the planner can be missing, and how it asks for it."""

    kind: str
    label: str
    question: str
    examples: list[str]


ASKS = [
    Ask(
        kind="income",
        label="Income",
        question="What comes in each month, and how often?",
        examples=["my salary is 1.5L a month", "I get 22k rent from a flat"],
    ),
    Ask(
        kind="expenses",
        label="Regular expenses",
        question="What goes out every month without you deciding?",
        examples=["rent is 35k and household about 20k", "insurance is 24k a year"],
    ),
    Ask(
        kind="emis",
        label="Loan EMIs",
        question="Are you repaying any loans, and how long is left?",
        examples=["home loan EMI 42k, 18 years left", "car loan 15k for 3 more years"],
    ),
    Ask(
        kind="sips",
        label="SIPs",
        question="What do you invest every month, so it is not counted as spare cash?",
        examples=["5k a month into Parag Parikh Flexi Cap", "10k into a Nifty index fund"],
    ),
]


def missing_kinds(held: dict[str, int]) -> list[str]:

    """List the record types this person has none of, in the order worth asking for them."""

    return [ask.kind for ask in ASKS if not held.get(ask.kind)]


def data_request(held: dict[str, int]) -> PromptBlock | None:

    """Build the block that asks for everything still missing, or nothing when the records are complete."""

    outstanding = [ask for ask in ASKS if not held.get(ask.kind)]

    if not outstanding:
        return None

    return PromptBlock(
        title=title_for(len(outstanding)),
        items=[
            PromptItem(label=ask.label, question=ask.question, examples=list(ask.examples))
            for ask in outstanding
        ],
        caption=ATTACH_NOTE,
    )


def title_for(outstanding: int) -> str:

    """Head the ask by how much is left, so someone part way through is not greeted as new."""

    if outstanding == len(ASKS):
        return "Tell me these four and I can answer anything about your month"

    return "A few more and the figures get sharper"


def spoken(kinds: list[str]) -> str:

    """Join record types into the phrase a plain text sentence can end on, for clients showing no blocks."""

    names = {ask.kind: ask.label.lower() for ask in ASKS}

    spoken_names = [names[kind] for kind in kinds]

    if not spoken_names:
        return ""

    if len(spoken_names) == 1:
        return spoken_names[0]

    return f"{', '.join(spoken_names[:-1])} and {spoken_names[-1]}"
