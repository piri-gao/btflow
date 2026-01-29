"""
MCP HTTP/SSE demo using fastmcp v2.

Run server:
    python examples/mcp_http_demo.py server

Run client (HTTP):
    python examples/mcp_http_demo.py client http

Run client (SSE):
    python examples/mcp_http_demo.py client sse
"""
import asyncio
import sys
from typing import Dict, Any

from btflow.protocols.mcp import MCPClient, MCPServer


def build_server() -> MCPServer:
    server = MCPServer(name="btflow-mcp-demo", description="BTFlow MCP HTTP/SSE demo server")

    def echo(text: str) -> Dict[str, Any]:
        return {"ok": True, "echo": text}

    def add(a: int, b: int) -> Dict[str, Any]:
        return {"ok": True, "result": a + b}

    server.add_tool(echo, name="echo", description="Echo text")
    server.add_tool(add, name="add", description="Add two integers")
    return server


async def run_client(transport: str):
    url = "http://localhost:8000"
    client = MCPClient(url, transport_type=transport)
    async with client:
        tools = await client.list_tools()
        print(f"🧰 Tools ({transport}): {[t.name for t in tools]}")
        result = await client.call_tool("add", {"a": 2, "b": 5})
        print("✅ add result:", result)


def main():
    if len(sys.argv) < 2:
        print("Usage: python examples/mcp_http_demo.py [server|client] [http|sse]")
        return

    mode = sys.argv[1]
    if mode == "server":
        server = build_server()
        print("🚀 Starting MCP server on http://localhost:8000 (transport=http)")
        server.run(transport="http", host="0.0.0.0", port=8000)
        return

    if mode == "client":
        transport = sys.argv[2] if len(sys.argv) > 2 else "http"
        asyncio.run(run_client(transport))
        return

    print("Unknown mode:", mode)


if __name__ == "__main__":
    main()
