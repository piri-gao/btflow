from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from btflow.core.logging import logger
from btflow.tools.base import Tool

try:
    from fastmcp import Client, FastMCP
    from fastmcp.client.transports import (
        PythonStdioTransport,
        SSETransport,
        StreamableHttpTransport,
        StdioTransport,
    )
    FASTMCP_AVAILABLE = True
except ImportError:
    FASTMCP_AVAILABLE = False
    Client = None
    FastMCP = None
    PythonStdioTransport = None
    SSETransport = None
    StreamableHttpTransport = None
    StdioTransport = None


@dataclass
class MCPServerConfig:
    command: str
    args: List[str] = field(default_factory=list)
    env: Optional[Dict[str, str]] = None


class MCPClient:
    """MCP client with multi-transport support (fastmcp v2)."""
    def __init__(
        self,
        server_source: Union[MCPServerConfig, str, List[str], "FastMCP", Dict[str, Any]],
        server_args: Optional[List[str]] = None,
        transport_type: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        **transport_kwargs,
    ):
        if not FASTMCP_AVAILABLE:
            raise RuntimeError(
                "fastmcp package not installed. Run: pip install fastmcp>=2.0.0"
            )

        self.server_args = server_args or []
        self.transport_type = transport_type
        self.env = env or {}
        self.transport_kwargs = transport_kwargs
        self.server_source = self._prepare_server_source(server_source)
        self.client: Optional[Client] = None
        self._context_manager = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def connect(self):
        if self.client is not None:
            return self.client

        self.client = Client(self.server_source)
        self._context_manager = self.client
        await self._context_manager.__aenter__()
        logger.info("🔌 [MCP] Connected to server.")
        return self.client

    async def close(self):
        """Close the MCP connection and cleanup subprocess transport.
        
        This method handles the cleanup of subprocess transports to avoid
        'Event loop is closed' errors during garbage collection.
        """
        if self._context_manager is None:
            return
        
        # Capture transport reference before closing
        transport = None
        if self.client is not None:
            transport = getattr(self.client, "transport", None)
        
        try:
            await self._context_manager.__aexit__(None, None, None)
        except Exception:
            pass  # Ignore errors during exit
        finally:
            self.client = None
            self._context_manager = None
        
        # For stdio transports (subprocesses), ensure clean shutdown
        if transport is not None:
            try:
                # Some transports have their own close method
                close_fn = getattr(transport, "close", None)
                if callable(close_fn):
                    import asyncio
                    result = close_fn()
                    if asyncio.iscoroutine(result):
                        await result
                
                # Give subprocess a moment to exit cleanly
                import asyncio
                await asyncio.sleep(0.1)
            except Exception:
                pass  # Ignore cleanup errors

    async def list_tools(self):
        client = await self.connect()
        response = await client.list_tools()
        if hasattr(response, "tools"):
            return response.tools
        if isinstance(response, list):
            return response
        return []

    async def list_resources(self):
        client = await self.connect()
        response = await client.list_resources()
        if hasattr(response, "resources"):
            return response.resources
        if isinstance(response, list):
            return response
        return []

    async def read_resource(self, uri: str):
        client = await self.connect()
        return await client.read_resource(uri)

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None):
        client = await self.connect()
        call_tool_mcp = getattr(client, "call_tool_mcp", None)
        if callable(call_tool_mcp):
            return await call_tool_mcp(name, arguments or {})
        return await client.call_tool(name, arguments or {})

    async def list_prompts(self):
        client = await self.connect()
        response = await client.list_prompts()
        if hasattr(response, "prompts"):
            return response.prompts
        if isinstance(response, list):
            return response
        return []

    async def get_prompt(self, name: str, arguments: Optional[Dict[str, str]] = None):
        client = await self.connect()
        return await client.get_prompt(name, arguments or {})

    async def ping(self) -> bool:
        client = await self.connect()
        try:
            await client.ping()
            return True
        except Exception:
            return False

    def get_transport_info(self) -> Dict[str, Any]:
        if not self.client:
            return {"status": "not_connected"}
        transport = getattr(self.client, "transport", None)
        if transport:
            return {
                "status": "connected",
                "transport_type": type(transport).__name__,
                "transport_info": str(transport),
            }
        return {"status": "unknown"}

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

    def _prepare_server_source(
        self,
        server_source: Union[MCPServerConfig, str, List[str], "FastMCP", Dict[str, Any]],
    ):
        if isinstance(server_source, MCPServerConfig):
            env = self.env or server_source.env
            return StdioTransport(
                command=server_source.command,
                args=server_source.args + self.server_args,
                env=env,
            )

        if FastMCP is not None and isinstance(server_source, FastMCP):
            return server_source

        if isinstance(server_source, dict):
            return self._create_transport_from_config(server_source)

        if isinstance(server_source, str) and (
            server_source.startswith("http://") or server_source.startswith("https://")
        ):
            transport_type = (self.transport_type or "http").lower()
            if transport_type == "sse":
                return SSETransport(url=server_source, **self.transport_kwargs)
            return StreamableHttpTransport(url=server_source, **self.transport_kwargs)

        if isinstance(server_source, str) and server_source.endswith(".py"):
            return PythonStdioTransport(
                script_path=server_source,
                args=self.server_args,
                env=self.env if self.env else None,
                **self.transport_kwargs,
            )

        if isinstance(server_source, list) and server_source:
            if server_source[0] == "python" and len(server_source) > 1 and server_source[1].endswith(".py"):
                return PythonStdioTransport(
                    script_path=server_source[1],
                    args=server_source[2:] + self.server_args,
                    env=self.env if self.env else None,
                    **self.transport_kwargs,
                )
            return StdioTransport(
                command=server_source[0],
                args=server_source[1:] + self.server_args,
                env=self.env if self.env else None,
                **self.transport_kwargs,
            )

        logger.debug("🔍 [MCP] Falling back to direct source: {}", server_source)
        return server_source

    def _create_transport_from_config(self, config: Dict[str, Any]):
        transport_type = config.get("transport", "stdio").lower()
        if transport_type == "stdio":
            args = config.get("args", [])
            env = config.get("env")
            cwd = config.get("cwd")
            if args and isinstance(args, list) and args[0].endswith(".py"):
                return PythonStdioTransport(
                    script_path=args[0],
                    args=args[1:] + self.server_args,
                    env=env,
                    cwd=cwd,
                    **self.transport_kwargs,
                )
            return StdioTransport(
                command=config.get("command", "python"),
                args=args + self.server_args,
                env=env,
                cwd=cwd,
                **self.transport_kwargs,
            )
        if transport_type == "sse":
            return SSETransport(
                url=config["url"],
                headers=config.get("headers"),
                auth=config.get("auth"),
                **self.transport_kwargs,
            )
        if transport_type == "http":
            return StreamableHttpTransport(
                url=config["url"],
                headers=config.get("headers"),
                auth=config.get("auth"),
                **self.transport_kwargs,
            )
        raise ValueError(f"Unsupported transport type: {transport_type}")


class MCPTool(Tool):
    """btflow Tool wrapper for MCP tools."""
    def __init__(self, client: MCPClient, tool_def: Any):
        self._client = client
        self._tool_def = tool_def
        self.name = getattr(tool_def, "name", "mcp_tool")
        self.description = getattr(tool_def, "description", "") or ""
        self.input_schema = getattr(tool_def, "inputSchema", {"type": "object"})
        self.output_schema = getattr(tool_def, "outputSchema", {"type": "string"})

    async def run(self, input: Any = None, **kwargs) -> Any:
        # If keyword arguments are provided, use them directly
        if kwargs:
            args = kwargs
        elif input is None:
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

        if getattr(result, "isError", False):
            content = getattr(result, "content", None)
            if isinstance(content, list):
                for block in content:
                    text = getattr(block, "text", None)
                    if text is not None:
                        return f"Error: {text}"
            return "Error: MCP tool execution failed"

        structured = getattr(result, "structuredContent", None)
        if structured is None:
            structured = getattr(result, "structured_content", None)
        if structured is not None:
            return structured

        content = getattr(result, "content", None)
        if isinstance(content, list):
            for block in content:
                text = getattr(block, "text", None)
                if text is not None:
                    return text
                data = getattr(block, "data", None)
                if data is not None:
                    return data
                blob = getattr(block, "blob", None)
                if blob is not None:
                    return blob

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
                data = getattr(item, "data", None)
                if data is not None:
                    return data
                blob = getattr(item, "blob", None)
                if blob is not None:
                    return blob
        return str(result)


__all__ = ["MCPServerConfig", "MCPClient", "MCPTool", "MCPResourceTool"]
