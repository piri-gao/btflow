import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from btflow.core.logging import logger
from btflow.tools.base import Tool


@dataclass
class MCPServerConfig:
    command: str
    args: List[str] = field(default_factory=list)
    env: Optional[Dict[str, str]] = None


class MCPClient:
    """Minimal MCP stdio client."""
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._session = None
        self._stdio_cm = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def connect(self):
        if self._session is not None:
            return self._session

        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as e:
            raise RuntimeError("mcp package not installed. Run: pip install \"mcp[cli]\"") from e

        params = StdioServerParameters(
            command=self.config.command,
            args=self.config.args,
            env=self.config.env,
        )
        self._stdio_cm = stdio_client(params)
        read, write = await self._stdio_cm.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()
        logger.info("🔌 [MCP] Connected to server: {} {}", self.config.command, self.config.args)
        return self._session

    async def close(self):
        if self._session is None:
            return
        try:
            await self._session.__aexit__(None, None, None)
        finally:
            self._session = None
            if self._stdio_cm is not None:
                await self._stdio_cm.__aexit__(None, None, None)
                self._stdio_cm = None

    async def list_tools(self):
        session = await self.connect()
        response = await session.list_tools()
        return response.tools

    async def list_resources(self):
        session = await self.connect()
        response = await session.list_resources()
        return response.resources

    async def read_resource(self, uri: str):
        session = await self.connect()
        return await session.read_resource(uri)

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None):
        session = await self.connect()
        return await session.call_tool(name, arguments=arguments or {})

    async def as_tools(self, allowlist: Optional[List[str]] = None) -> List["MCPTool"]:
        tools = await self.list_tools()
        allow = set(t.lower() for t in allowlist) if allowlist else None
        result = []
        for tool in tools:
            if allow and tool.name.lower() not in allow:
                continue
            result.append(MCPTool(self, tool))
        return result

    async def as_resource_tools(self, allowlist: Optional[List[str]] = None) -> List["MCPResourceTool"]:
        resources = await self.list_resources()
        allow = set(r.lower() for r in allowlist) if allowlist else None
        result = []
        for resource in resources:
            uri = getattr(resource, "uri", "")
            if allow and uri.lower() not in allow:
                continue
            result.append(MCPResourceTool(self, resource))
        return result


class MCPTool(Tool):
    """btflow Tool wrapper for MCP tools."""
    def __init__(self, client: MCPClient, tool_def: Any):
        self._client = client
        self._tool_def = tool_def
        self.name = getattr(tool_def, "name", "mcp_tool")
        self.description = getattr(tool_def, "description", "") or ""
        self.input_schema = getattr(tool_def, "inputSchema", {"type": "object"})
        self.output_schema = getattr(tool_def, "outputSchema", {"type": "string"})

    async def run(self, input: Any) -> Any:
        if input is None:
            args = {}
        elif isinstance(input, dict):
            args = input
        else:
            args = {"input": input}
            if isinstance(self.input_schema, dict):
                props = self.input_schema.get("properties")
                if isinstance(props, dict) and len(props) == 1:
                    key = next(iter(props.keys()))
                    args = {key: input}

        result = await self._client.call_tool(self.name, arguments=args)

        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            return structured

        content = getattr(result, "content", None)
        if isinstance(content, list):
            for block in content:
                text = getattr(block, "text", None)
                if text is not None:
                    return text

        return str(result)


class MCPResourceTool(Tool):
    """Read-only Tool wrapper for MCP resources."""
    def __init__(self, client: MCPClient, resource_def: Any):
        self._client = client
        self._resource_def = resource_def
        self.name = getattr(resource_def, "name", None) or getattr(resource_def, "uri", "mcp_resource")
        self.description = getattr(resource_def, "description", "") or ""
        self.input_schema = {"type": "string", "description": "Resource URI (optional override)"}
        self.output_schema = {"type": "string"}

    async def run(self, input: Any) -> Any:
        uri = getattr(self._resource_def, "uri", None)
        if isinstance(input, str) and input:
            uri = input
        if not uri:
            return "Error: resource URI not provided"
        result = await self._client.read_resource(uri)

        contents = getattr(result, "contents", None)
        if isinstance(contents, list):
            for item in contents:
                text = getattr(item, "text", None)
                if text is not None:
                    return text
        return str(result)


__all__ = ["MCPServerConfig", "MCPClient", "MCPTool", "MCPResourceTool"]
