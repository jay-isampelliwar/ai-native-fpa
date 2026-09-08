"""The two nodes of the graph, and nothing else.

    authenticate_context -> run_agent

Seven nodes used to live here, then four, now two. What went and why is worth keeping written down,
because each removal traded a guarantee for a smaller file and the guarantees are not coming back on
their own.

``validate_skill_result`` checked a skill's returned status against its registered definition. There
are no definitions now, so the situation it protected against cannot arise. ``request_approval`` and
``controlled_write`` were the interrupt and the write behind it; the tools write when called, by
explicit product decision, so the pause had nothing left to pause. ``write_audit_record`` called the
recorder on every path, which meant a request could not answer a person without leaving a trail - with
the approval interrupt already gone that row was the last record of what the agent did to somebody's
records, and nothing replaces it. ``respond`` picked between a refusal reason and the answer already
in state, which ``run_agent`` does itself in the branch that produces the refusal.

The helpers went the same way and for a plainer reason: fourteen module level functions to run one
agent read as machinery rather than as a turn. What survives is inlined into ``run_agent``, so the
whole of a turn is one function a reader can hold in their head.

Three of those helpers were a figure check, and losing it is the removal with teeth. Every number in a
reply used to be compared against the numbers the tools had returned, and a reply quoting one that
appeared nowhere was set aside in favour of a tool's own wording. That is what made "quote figures,
do not derive them" a rule rather than a request in the prompt. It is now a request. A model that adds
two rows together and reports the total will be believed.

Four more were the token stream - ``speak``, ``say``, ``stream_writer``, ``reaching_for``. The agent is
a graph of its own invoked inside another graph, so it inherited neither the parent's token stream nor
its writer, and those four bridged the gap. One ``ainvoke`` replaces them: ``/messages/stream`` still
answers, but it sends the finished reply in one piece rather than as it is written.

``authenticate_context`` still runs first and still mints the correlation id everything else is logged
against. In this phase ``local_user`` grants every scope, so it is wiring rather than a decision - but
it is the seam a real credential lands in, and the agent's tools are bound to the context it produces.

``run_agent`` is the rest. It replaced eleven skills, a registry, a result validator and an approval
interrupt, because a skill was the wrong unit: "Show my SIPs" reached a skill for changing one, then a
skill for holdings, and got an apology from each, since listing SIPs had never been anybody's job.
Every question falling between two skills produced that shape of answer, and the fix was not a twelfth
skill. There is one agent and twenty two tools, sized to the questions people actually ask.

The agent is rebuilt every turn rather than cached, because its tools are closed over this caller's
context. A cached agent would hold the first caller's user id in every tool it owns, which is the one
bug in this file worth being paranoid about: it would not fail, it would answer the wrong person.

The recursion limit is real and derived from the settings rather than left at the library default. A
tool set this size makes a loop cheap to enter - list, update, list again - and an agent that cannot
stop is a bill as well as a hung request.

History comes from the transcript rather than the checkpointer, so what the model remembers and what
the person can scroll back to are the same rows. An unreadable transcript is treated as no memory
rather than as a failed turn, because a person asking a fresh question does not care that the
scrollback is broken.

``denial_reason`` stays in the state even though no node reads it, because the planner API classifies
a turn as refused from that field.
"""

from langchain.agents import create_agent
from langgraph.errors import GraphRecursionError

from app.agent.prompt import SYSTEM_PROMPT, records_held
from app.agent.state import AgentContext, PlannerState, RunLog
from app.agent.tools import build_tools
from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import local_user, new_correlation_id

log = get_logger("agent")

FALLBACK = "I could not work that out just now."

NO_CALLER = "the agent was reached without a caller"


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


async def run_agent(state: PlannerState) -> dict:

    """Answer this message with the full tool set, and report which tools ran and what they changed."""

    from app.repositories.conversations_repository import conversations_repository
    from app.services.llm_service import get_explanation_model

    if state.context is None:
        return {"denial_reason": NO_CALLER, "response": f"I could not do that: {NO_CALLER}"}

    context = AgentContext(**state.context.model_dump())

    run = RunLog()

    held = await records_held(context.user_id)

    agent = create_agent(
        model=get_explanation_model(),
        tools=build_tools(context, run),
        system_prompt=f"{SYSTEM_PROMPT}\n\n{held}",
    )

    history: list[tuple[str, str]] = []

    try:
        transcript = await conversations_repository.transcript(context.user_id, context.conversation_id)

        earlier = (transcript[:-1] if transcript else [])[-settings.conversation_memory_turns :]

        history = [("assistant" if row.role == "planner" else "user", row.text) for row in earlier if row.text]

    except Exception:
        log.warning("history could not be read", conversation_id=context.conversation_id, exc_info=True)

    try:
        finished = await agent.ainvoke(
            {"messages": [*history, ("user", state.user_message)]},
            config={"recursion_limit": settings.agent_recursion_limit},
        )

    except GraphRecursionError:

        log.warning("agent did not settle", user_id=context.user_id)

        return {
            "response": "I went round in circles on that one. Could you ask it a step at a time?",
            "tools_used": run.tools,
            "writes_performed": run.writes,
        }

    except Exception:

        log.warning("agent failed", user_id=context.user_id, exc_info=True)

        return {"response": FALLBACK, "tools_used": run.tools, "writes_performed": run.writes}

    spoken = [
        message.content.strip()
        for message in finished.get("messages", [])
        if getattr(message, "type", "") == "ai"
        and isinstance(getattr(message, "content", ""), str)
        and message.content.strip()
    ]

    return {
        "response": spoken[-1] if spoken else FALLBACK,
        "tools_used": run.tools,
        "writes_performed": run.writes,
    }
