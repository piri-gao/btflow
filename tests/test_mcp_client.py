import asyncio
import unittest

from btflow.tools.mcp_client import MCPTool


class DummyToolDef:
    name = "dummy"
    description = "dummy tool"
    inputSchema = {"type": "object"}
    outputSchema = {"type": "string"}


class DummyClient:
    def __init__(self):
        self.called = None
        self.return_structured = None

    async def call_tool(self, name, arguments=None):
        self.called = (name, arguments)
        if self.return_structured is not None:
            return type("Res", (), {"structuredContent": self.return_structured, "content": []})()
        text_block = type("Text", (), {"text": "ok"})()
        return type("Res", (), {"structuredContent": None, "content": [text_block]})()


class TestMCPTool(unittest.IsolatedAsyncioTestCase):
    async def test_wraps_non_dict_input(self):
        client = DummyClient()
        tool = MCPTool(client, DummyToolDef())
        result = await tool.run("hi")
        self.assertEqual(result, "ok")
        self.assertEqual(client.called, ("dummy", {"input": "hi"}))

    async def test_structured_content_preferred(self):
        client = DummyClient()
        client.return_structured = {"result": 1}
        tool = MCPTool(client, DummyToolDef())
        result = await tool.run({"a": 1})
        self.assertEqual(result, {"result": 1})
        self.assertEqual(client.called, ("dummy", {"a": 1}))


if __name__ == "__main__":
    asyncio.run(unittest.main())
