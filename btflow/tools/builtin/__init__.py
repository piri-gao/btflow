"""Built-in tools for btflow agents."""

from btflow.tools.builtin.calculator import CalculatorTool
from btflow.tools.builtin.python_repl import PythonREPLTool
from btflow.tools.builtin.file import FileReadTool, FileWriteTool

def _missing_tool(name: str, package: str):
    class _MissingTool:
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                f"{name} requires optional dependency '{package}'. "
                f"Install it with: pip install {package}"
            )

    _MissingTool.__name__ = name
    return _MissingTool


# Optional tools with external dependencies
try:
    from btflow.tools.builtin.http import HTTPTool
except ImportError:
    HTTPTool = _missing_tool("HTTPTool", "aiohttp")

try:
    from btflow.tools.builtin.duckduckgo import DuckDuckGoSearchTool
except ImportError:
    DuckDuckGoSearchTool = _missing_tool("DuckDuckGoSearchTool", "duckduckgo-search")

__all__ = [
    "CalculatorTool",
    "PythonREPLTool",
    "FileReadTool",
    "FileWriteTool",
    "HTTPTool",
    "DuckDuckGoSearchTool",
]
