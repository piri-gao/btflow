"""btflow tools module - Tool base class and built-in tools."""

from btflow.tools.base import Tool
from btflow.tools.node import ToolNode
from btflow.tools.base import execute_tool
from btflow.tools.decorators import tool, FunctionTool
from btflow.tools.builtin import (
    CalculatorTool,
    PythonREPLTool,
    FileReadTool,
    FileWriteTool,
)
from btflow.tools.builtin.mock import MockSearchTool, MockWikipediaTool

# Re-export optional tools (may be None if dependencies not installed)
from btflow.tools.builtin import HTTPTool, DuckDuckGoSearchTool

__all__ = [
    # Core
    "Tool",
    "ToolNode",
    "execute_tool",
    "tool",
    "FunctionTool",
    # Built-in tools
    "CalculatorTool",
    "MockSearchTool",
    "MockWikipediaTool",
    "PythonREPLTool",
    "FileReadTool",
    "FileWriteTool",
    "HTTPTool",
    "DuckDuckGoSearchTool",
]
