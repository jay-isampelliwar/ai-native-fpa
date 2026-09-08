"""The single ReAct agent that answers every turn, and the node the graph calls to run it.

This replaced eleven skills, a registry, a result validator and an approval interrupt. The reason was
not that the skills were badly built - it was that a skill is the wrong unit. "Show my SIPs" reached a
skill for changing one, then a skill for holdings, and got an apology from each, because listing SIPs
had never been anybody's job. Every question that fell between two skills produced that shape of
answer, and the fix was not a twelfth skill.

So there is one agent and twenty two tools, sized to the questions people actually ask. What the model
chooses is which tools to call and what to say; what it never chooses is what a figure is - every
derived number still comes from a versioned calculator, and the reply is checked against the numbers
the tools returned before anyone sees it.

The agent is rebuilt every turn rather than cached, because its tools are closed over this caller's
context. A cached agent would hold the first caller's user id in every tool it owns, which is the one
bug in this file worth being paranoid about: it would not fail, it would answer the wrong person.

Streaming works the way it did before and for the same reason. The agent is a graph of its own invoked
inside another graph, so it inherits neither the parent's token stream nor its writer; this node
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

What is deliberately absent: any notion of a chosen skill, a permission gate before the run, or a
proposal awaiting approval. Phase 1 grants every scope to the local caller, so the previous gate was
wiring rather than a decision, and the approval interrupt was removed by explicit product decision -
the tools write when called. ``app.agent.tools.writes`` is where that trade is described.
"""

from langchain.agents import create_agent
from langgraph.errors import GraphRecursionError

from app.agent.context import AgentContext, RunLog
from app.agent.narration import invents_figures
from app.agent.prompt import SYSTEM_PROMPT, label_for, records_held
from app.agent.tools import build_tools
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("agent")

ANSWER_NODE = "model"

FALLBACK = "I could not work that out just now."

SET_ASIDE = (
    "I had an answer for that but it quoted a figure I could not trace back to your records, so I am "
    "not showing it. Ask me again and I will read the records properly this time."
)


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
