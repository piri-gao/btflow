"""btflow tools module - Tool base class and built-in tools."""

from btflow.tools.base import Tool
from btflow.tools.node import ToolNode
from btflow.tools.execution import execute_tool
from btflow.tools.builtin import (
    CalculatorTool,
    PythonREPLTool,
    FileReadTool,
    FileWriteTool,
)
from btflow.tools.mock import SearchTool, WikipediaTool

# Re-export optional tools (may be None if dependencies not installed)
from btflow.tools.builtin import HTTPTool, DuckDuckGoSearchTool

__all__ = [
    # Core
    "Tool",
    "ToolNode",
    "execute_tool",
    # Built-in tools
    "CalculatorTool",
    "SearchTool",
    "WikipediaTool",
    "PythonREPLTool",
    "FileReadTool",
    "FileWriteTool",
    "HTTPTool",
    "DuckDuckGoSearchTool",
]
