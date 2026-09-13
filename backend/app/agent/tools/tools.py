"""The one list of tools the agent is bound to, gathered from the four modules that define them."""

from app.agent.tools.analysis import ANALYSIS_TOOLS
from app.agent.tools.imports import IMPORT_TOOLS
from app.agent.tools.reads import READ_TOOLS
from app.agent.tools.writes import WRITE_TOOLS

TOOLS = [*READ_TOOLS, *ANALYSIS_TOOLS, *IMPORT_TOOLS, *WRITE_TOOLS]
