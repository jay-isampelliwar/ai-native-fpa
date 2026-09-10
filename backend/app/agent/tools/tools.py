from app.agent.tools.analysis import build_analysis_tools
from app.agent.tools.reads import build_read_tools
from app.agent.tools.writes import build_write_tools

TOOLS = [
    *build_analysis_tools,
    *build_read_tools,
    *build_write_tools,
    ]