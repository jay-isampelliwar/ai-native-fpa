"""The four nodes of the graph, and everything they need to do their work.

The nodes come first in this file because they are its subject; the helpers each one leans on follow
underneath. Read top to bottom and you get the shape of a turn before the machinery of one.

    authenticate_context -> run_agent -> write_audit_record -> respond

Three of these were never about choosing anything: identify the caller, record what happened, say it.
Seven nodes used to live here. ``validate_skill_result`` checked a skill's returned status against its
registered definition - there are no definitions now, and the property it protected most, a skill
claiming a completed write when its definition required approval, describes a situation that cannot
arise. ``request_approval`` and ``controlled_write`` were the interrupt and the write behind it; the
tools write directly by explicit product decision, so the pause has nothing left to pause.
``app.agent.tools.writes`` carries the description of that trade.

``authenticate_context`` still runs first and still mints the correlation id everything else is logged
against. In this phase ``local_user`` grants every scope, so it is wiring rather than a decision - but
it is the seam a real credential lands in, and the agent's tools are bound to the context it produces.

``run_agent`` is the whole of the middle. It replaced eleven skills, a registry, a result validator
and an approval interrupt. The reason was not that the skills were badly built - it was that a skill
is the wrong unit. "Show my SIPs" reached a skill for changing one, then a skill for holdings, and got
an apology from each, because listing SIPs had never been anybody's job. Every question that fell
between two skills produced that shape of answer, and the fix was not a twelfth skill.

So there is one agent and twenty two tools, sized to the questions people actually ask. What the model
chooses is which tools to call and what to say; what it never chooses is what a figure is - every
derived number still comes from a versioned calculator, and the reply is checked against the numbers
the tools returned before anyone sees it.

The agent is rebuilt every turn rather than cached, because its tools are closed over this caller's
context. A cached agent would hold the first caller's user id in every tool it owns, which is the one
bug in this file worth being paranoid about: it would not fail, it would answer the wrong person.

Streaming works the way it did before and for the same reason. The agent is a graph of its own invoked
inside another graph, so it inherits neither the parent's token stream nor its writer; the node
iterates the agent's stream and pushes each piece through the writer it captured. Only tokens from the
answer node are forwarded - anything a tool emits internally arrives under a different node and is not
the person's answer.

Tool calls are announced when the model asks for one, not when it starts. Those are the same instant
in wall clock terms and seconds apart in experience, because the request arrives in the token stream
while the tool itself waits for the whole model turn to finish. Announcing on the request is what
fills the silence somebody would otherwise spend watching "Thinking".

The recursion limit is real and derived from the settings rather than left at the library default. A
tool set this size makes a loop cheap to enter - list, update, list again - and an agent that cannot
stop is a bill as well as a hung request.

History comes from the transcript rather than the checkpointer, so what the model remembers and what
the person can scroll back to are the same rows.

The record counts in the prompt count as a source for the figure check, and leaving them out was a
bug worth naming. Those counts are read from the database, so a reply saying "you have one goal"
without calling a tool is quoting the planner's own reading - but the check only knew about tool
results, so it set that answer aside and showed a failure message instead of a correct sentence. A
figure the prompt was given is a figure the reply may repeat.

``write_audit_record`` sits in front of ``respond`` on every path, including the failure path, so a
request cannot answer a person without leaving a trail. It records which tools ran and what they
changed rather than which skill was routed to.

``respond`` chooses between what is already in state and writes nothing of its own. The sentence a
person reads was settled by ``settle`` below, where the figure check had already had its say; adding a
second model call here could only reword an answer that is already in the planner's own words, and
could only introduce a figure the first one was prevented from inventing.

Nodes return a dict of state updates rather than a mutated ``PlannerState``, so each node's
contribution is explicit and a node that returns nothing has provably changed nothing.

Failure is expressed in state, not by raising. A refusal records a ``denial_reason`` and still reaches
the audit node and still owes the person an explanation, both of which an exception would skip.

What is deliberately absent: any notion of a chosen skill, a permission gate before the run, or a
proposal awaiting approval. Phase 1 grants every scope to the local caller, so the previous gate was
wiring rather than a decision, and the approval interrupt was removed by explicit product decision -
the tools write when called.

The figure check at the bottom of this file is what makes "quote figures, do not derive them" a rule
rather than a request. Every number in the reply is compared against the numbers in what the tools
returned, and a reply carrying one that was not there is set aside.

It is a check and not a gate, and the difference is worth stating. It cannot tell a correct sum from
an incorrect one - only that a number was not returned by anything - so it catches invention and would
miss a figure that happened to be quoted correctly from the wrong row.

A reply written in words rather than digits - "2.26 lakh" for 226,000 - is still set aside. Not
because it is wrong, but because a model that reformats a figure may reformat it wrongly, and there is
a correct sentence to fall back to.

Comparison is numeric rather than textual, and it has to be. Tools return money as it is stored -
"10000.00" - and a model quoting that writes "10,000", which as bare digit strings are "1000000" and
"10000" and share nothing. Stripping non digits was adequate while skills returned finished sentences
with figures already rendered; against raw rows it rejected almost every correct answer. So each match
is parsed as a number and canonicalised, which makes "10000.00", "10,000" and "10000" one value and
leaves a genuinely invented total with nothing to match. Grouping, currency prefixes and trailing
zeros therefore all wash out, and "1,00,000" - Indian grouping, which a model will produce -
normalises the same as "100000".

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

from langchain.agents import create_agent
from langgraph.errors import GraphRecursionError

from app.agent.prompt import SYSTEM_PROMPT, label_for, records_held
from app.agent.state import AgentContext, PlannerState, RunLog
from app.agent.tools import build_tools
from app.audit.recorder import recorder
from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import local_user, new_correlation_id

log = get_logger("agent")

ANSWER_NODE = "model"

FALLBACK = "I could not work that out just now."

SET_ASIDE = (
    "I had an answer for that but it quoted a figure I could not trace back to your records, so I am "
    "not showing it. Ask me again and I will read the records properly this time."
)

NUMBER = re.compile(r"(?<![A-Za-z0-9_])\d[\d,]*(?:\.\d+)?(?![A-Za-z0-9_])")

ORDINAL = re.compile(r"^[ \t]*\d+[.)]\s", re.MULTILINE)


def authenticate_context(state: PlannerState) -> dict:

    """Resolve the caller and mint the correlation id, producing the context every tool is bound to."""

    user = local_user(state.user_id)

    context = AgentContext(
        user_id=user.user_id,
        conversation_id=state.conversation_id,
        correlation_id=new_correlation_id(),
        timezone=settings.default_timezone,
        currency=settings.default_currency,
    )

    return {"user": user, "context": context}


async def run_agent(state) -> dict:

    """Answer this message with the full tool set, and report what the turn read, computed and changed."""

    if state.context is None:
        return {"denial_reason": "the agent was reached without a caller"}

    context = AgentContext(**state.context.model_dump())

    run = RunLog()

    held = await records_held(context.user_id)

    agent = create_agent(
        model=explanation_model(),
        tools=build_tools(context, run),
        system_prompt=f"{SYSTEM_PROMPT}\n\n{held}",
    )

    history = await recall(context.user_id, context.conversation_id)

    try:
        finished = await speak(agent, [*history, ("user", state.user_message)], stream_writer())

    except GraphRecursionError:

        log.warning("agent did not settle", user_id=context.user_id)

        return outcome(state, run, "I went round in circles on that one. Could you ask it a step at a time?")

    except Exception as exc:

        log.warning("agent failed", error=type(exc).__name__, exc_info=True)

        return outcome(state, run, FALLBACK)

    run.returned = tool_results(finished)

    return outcome(state, run, settle(final_text(finished), run, state.user_message, held))


async def write_audit_record(state: PlannerState) -> dict:

    """Capture what this turn read, computed and changed, for every outcome including failures."""

    await recorder.record(state)

    return {}


def respond(state: PlannerState) -> dict:

    """Choose the single message the person reads, preferring a refusal reason over an empty answer."""

    if state.denial_reason:
        return {"response": f"I could not do that: {state.denial_reason}"}

    if state.response:
        return {}

    return {"response": "I could not produce an answer for that request."}


def stream_writer():

    """Take the writer for the run this node is inside, or nothing when nobody is streaming."""

    try:
        from langgraph.config import get_stream_writer

        return get_stream_writer()

    except Exception:
        return None


def say(writer, payload: dict) -> None:

    """Push one line to whoever is listening, never failing the turn because nobody is."""

    if writer is None:
        return

    try:
        writer(payload)

    except Exception:
        return


def reaching_for(message) -> list[str]:

    """Name the tools this chunk is asking for, which is known well before the tool starts running."""

    chunks = getattr(message, "tool_call_chunks", None) or []

    return [chunk["name"] for chunk in chunks if chunk.get("name")]


async def speak(agent, messages: list, writer) -> dict:

    """Run the agent, forwarding the words of its answer as they are written when anyone is listening."""

    config = {"recursion_limit": settings.agent_recursion_limit}

    if writer is None:
        return await agent.ainvoke({"messages": messages}, config=config)

    finished: dict = {}

    announced: set[str] = set()

    async for mode, chunk in agent.astream(
        {"messages": messages},
        config=config,
        stream_mode=["messages", "values"],
    ):

        if mode == "values":

            finished = chunk

            continue

        message, metadata = chunk

        if metadata.get("langgraph_node") != ANSWER_NODE:
            continue

        for name in reaching_for(message):

            if name in announced:
                continue

            announced.add(name)

            say(writer, {"tool": name, "label": label_for(name)})

        content = getattr(message, "content", "")

        if isinstance(content, str) and content:
            say(writer, {"token": content})

    return finished


def final_text(state) -> str:

    """Take the model's last spoken message out of the finished agent state."""

    for message in reversed(state.get("messages", [])):

        text = getattr(message, "content", "")

        if isinstance(text, str) and text.strip() and getattr(message, "type", "") == "ai":
            return text.strip()

    return ""


def tool_results(state) -> list[str]:

    """Collect what every tool returned this turn, which is the set of figures the reply may quote."""

    returned = []

    for message in state.get("messages", []):

        if getattr(message, "type", "") != "tool":
            continue

        content = getattr(message, "content", "")

        if isinstance(content, str) and content:
            returned.append(content)

    return returned


async def recall(user_id: int, conversation_id: str) -> list[tuple[str, str]]:

    """Read this conversation's earlier turns, treating an unreadable transcript as no memory at all."""

    from app.repositories.conversations_repository import conversations_repository

    try:
        transcript = await conversations_repository.transcript(user_id, conversation_id)

    except Exception:

        log.warning("history could not be read", conversation_id=conversation_id, exc_info=True)

        return []

    recent = (transcript[:-1] if transcript else [])[-settings.conversation_memory_turns :]

    return [("assistant" if row.role == "planner" else "user", row.text) for row in recent if row.text]


def settle(reply: str, log_of_run: RunLog, question: str, held: str) -> str:

    """Choose the sentence the person reads, refusing one that quotes a figure nothing gave it."""

    sources = [*log_of_run.returned, *log_of_run.spoken, question, held]

    if reply and not invents_figures(reply, sources):
        return reply

    log.warning("reply set aside", tools=log_of_run.tools, reply=reply[:120])

    if log_of_run.spoken:
        return log_of_run.spoken[-1]

    if log_of_run.writes:
        return f"Done - {', '.join(log_of_run.writes)}."

    if reply:
        return SET_ASIDE

    return FALLBACK


def outcome(state, run: RunLog, reply: str) -> dict:

    """Shape one finished turn into the state updates the rest of the graph reads."""

    return {
        "response": reply,
        "tools_used": run.tools,
        "writes_performed": run.writes,
        "blocks": run.blocks,
        "evidence_ids": run.evidence_ids,
        "calculator_versions": run.calculator_versions,
        "assumptions": run.assumptions,
    }


def explanation_model():

    """Build the model that answers, kept behind a function so tests can replace it in one place."""

    from app.services.llm_service import get_explanation_model

    return get_explanation_model()


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
