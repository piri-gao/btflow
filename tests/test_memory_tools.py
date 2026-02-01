import os
import sys

# Ensure repo root is on sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from btflow.memory import Memory
from btflow.memory.tools import MemoryAddTool, MemorySearchTool


@pytest.mark.asyncio
async def test_memory_tools_with_memory():
    memory = Memory(max_size=5)
    add_tool = MemoryAddTool(memory)
    search_tool = MemorySearchTool(memory)

    result = await add_tool.run(content="hello world")
    assert "Stored" in result

    search_result = await search_tool.run(query="hello", k=3)
    assert "hello" in search_result
