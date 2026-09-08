"""The complete tool set one turn is given, assembled in one list a reviewer can read.

There is no registry here and no discovery. The tools a turn can reach are exactly the three lists
below, concatenated, and that is on purpose: the previous design had a skill registry precisely so an
untrusted routed name could not reach anything unregistered, and the same property is now free -
nothing resolves a name at all, because the model is handed function objects rather than asked for
one.

Every tool is built per request and closed over one ``AgentContext`` and one ``RunLog``. That is what
makes ownership structural: no tool has a user parameter, so there is no argument the model could put
somebody else's id into. It is also what lets the log collect blocks and evidence from calls several
frames deep without any of them knowing about the response.

The order is reads, then analysis, then writes, and it is the order the prompt tells the model to work
in - look, compute, then change. Tool order does not bind a model to anything, but it costs nothing
and it matches how the set is meant to be used.
"""

from langchain_core.tools import BaseTool

from app.agent.state import AgentContext, RunLog
from app.agent.tools.analysis import build_analysis_tools
from app.agent.tools.reads import build_read_tools
from app.agent.tools.writes import build_write_tools


def build_tools(context: AgentContext, log: RunLog) -> list[BaseTool]:

    """Assemble every tool this turn may call, each bound to this caller and this run's log."""

    return [
        *build_read_tools(context, log),
        *build_analysis_tools(context, log),
        *build_write_tools(context, log),
    ]
