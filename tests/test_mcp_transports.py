import os
import tempfile
import unittest

import pytest

fastmcp = pytest.importorskip("fastmcp")

from btflow.protocols.mcp import MCPClient, MCPServerConfig

from fastmcp.client.transports import (
    PythonStdioTransport,
    SSETransport,
    StreamableHttpTransport,
    StdioTransport,
)


class TestMCPClientTransports(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, path = tempfile.mkstemp(suffix=".py")
        os.close(fd)
        cls._tmp_script = path

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "_tmp_script", None):
            try:
                os.unlink(cls._tmp_script)
            except FileNotFoundError:
                pass
    def test_stdio_config_transport(self):
        config = MCPServerConfig(command="python", args=[self._tmp_script])
        client = MCPClient(config)
        self.assertIsInstance(client.server_source, StdioTransport)

    def test_python_script_transport(self):
        client = MCPClient(self._tmp_script)
        self.assertIsInstance(client.server_source, PythonStdioTransport)

    def test_command_list_transport(self):
        client = MCPClient(["python", self._tmp_script])
        self.assertIsInstance(client.server_source, PythonStdioTransport)

        client2 = MCPClient(["node", "server.js"])
        self.assertIsInstance(client2.server_source, StdioTransport)

    def test_http_transport(self):
        client = MCPClient("http://localhost:8000")
        self.assertIsInstance(client.server_source, StreamableHttpTransport)

    def test_sse_transport(self):
        client = MCPClient("http://localhost:8000", transport_type="sse")
        self.assertIsInstance(client.server_source, SSETransport)

    def test_dict_transport(self):
        client = MCPClient({"transport": "http", "url": "http://localhost:8000"})
        self.assertIsInstance(client.server_source, StreamableHttpTransport)

        client2 = MCPClient({"transport": "sse", "url": "http://localhost:8000"})
        self.assertIsInstance(client2.server_source, SSETransport)

        client3 = MCPClient({
            "transport": "stdio",
            "command": "python",
            "args": [self._tmp_script],
        })
        self.assertIsInstance(client3.server_source, PythonStdioTransport)


if __name__ == "__main__":
    unittest.main()
