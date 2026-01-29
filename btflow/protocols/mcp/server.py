"""
Minimal MCP server wrapper (fastmcp v2).
"""
from typing import Any, Callable, Dict, Optional

try:
    from fastmcp import FastMCP
except ImportError as e:
    raise RuntimeError(
        "fastmcp package not installed. Run: pip install fastmcp>=2.0.0"
    ) from e


class MCPServer:
    """Thin wrapper around FastMCP for convenience."""

    def __init__(self, name: str, description: Optional[str] = None):
        self.mcp = FastMCP(name=name)
        self.name = name
        self.description = description or f"{name} MCP Server"

    def add_tool(self, func: Callable, name: Optional[str] = None, description: Optional[str] = None):
        if name or description:
            self.mcp.tool(name=name, description=description)(func)
        else:
            self.mcp.tool()(func)

    def add_resource(
        self,
        func: Callable,
        uri: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ):
        if uri:
            self.mcp.resource(uri)(func)
        else:
            self.mcp.resource()(func)

    def add_prompt(self, func: Callable, name: Optional[str] = None, description: Optional[str] = None):
        if name or description:
            self.mcp.prompt(name=name, description=description)(func)
        else:
            self.mcp.prompt()(func)

    def run(self, transport: str = "stdio", **kwargs):
        self.mcp.run(transport=transport, **kwargs)

    def get_info(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "protocol": "MCP",
        }


class MCPServerBuilder:
    """Chainable MCP server builder."""

    def __init__(self, name: str, description: Optional[str] = None):
        self.server = MCPServer(name, description)

    def with_tool(self, func: Callable, name: Optional[str] = None, description: Optional[str] = None):
        self.server.add_tool(func, name, description)
        return self

    def with_resource(
        self,
        func: Callable,
        uri: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ):
        self.server.add_resource(func, uri, name, description)
        return self

    def with_prompt(self, func: Callable, name: Optional[str] = None, description: Optional[str] = None):
        self.server.add_prompt(func, name, description)
        return self

    def build(self) -> MCPServer:
        return self.server

    def run(self, transport: str = "stdio", **kwargs):
        self.server.run(transport=transport, **kwargs)


__all__ = ["MCPServer", "MCPServerBuilder"]
