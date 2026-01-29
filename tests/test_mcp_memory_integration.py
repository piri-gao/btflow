import unittest

from fastmcp import FastMCP

from btflow.protocols.mcp import MCPClient


class TestMCPMemoryIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_memory_transport_tools_and_prompts(self):
        server = FastMCP("btflow-memory-mcp")

        @server.tool()
        def add(a: int, b: int) -> dict:
            return {"sum": a + b}

        @server.prompt()
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        async with MCPClient(server) as client:
            tools = await client.list_tools()
            self.assertTrue(any(t.name == "add" for t in tools))

            result = await client.call_tool("add", {"a": 2, "b": 3})
            # FastMCP returns ToolResult content; our MCPTool handles content decoding,
            # but raw client should still return something.
            self.assertIsNotNone(result)

            prompts = await client.list_prompts()
            self.assertTrue(any(p.name == "greet" for p in prompts))

            prompt = await client.get_prompt("greet", {"name": "BTFlow"})
            self.assertIsNotNone(prompt)


if __name__ == "__main__":
    unittest.main()
