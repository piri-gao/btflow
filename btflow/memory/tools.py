"""
Memory Tools - Expose memory as Agent-callable tools.
"""
from typing import Optional

from btflow.tools import Tool
from btflow.memory.memory import Memory
from btflow.memory.retriever import SearchOptions


class MemorySearchTool(Tool):
    """Search for relevant memories."""

    name = "search_memory"
    description = "Search your memory for relevant information."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to search for in memory",
            },
            "k": {
                "type": "integer",
                "description": "Number of results to return (default: 3)",
            },
            "mode": {
                "type": "string",
                "description": "Search mode: semantic, keyword, or hybrid",
            },
        },
        "required": ["query"],
    }
    output_schema = {"type": "string"}

    def __init__(self, memory: Memory):
        self._memory = memory

    async def run(self, query: str = None, k: int = 3, mode: str = None, **kwargs) -> str:
        if query is None:
            query = kwargs.get("input", "")
        if not query:
            return "Error: No query provided"
        if mode is None:
            mode = kwargs.get("mode")

        options = SearchOptions(k=k, mode=mode or "hybrid")
        items = self._memory.search(query, options=options)
        if not items:
            return "No relevant memories found."
        results = []
        for i, item in enumerate(items, 1):
            results.append(f"{i}. {item.text}")
        return "\n".join(results)


class MemoryAddTool(Tool):
    """Add new information to memory."""

    name = "add_memory"
    description = "Store important information in memory for future reference."
    input_schema = {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Information to remember",
            },
            "category": {
                "type": "string",
                "description": "Optional category (e.g., 'user_preference', 'fact', 'context')",
            },
            "metadata": {
                "type": "object",
                "description": "Optional metadata object to store with the memory",
            },
        },
        "required": ["content"],
    }
    output_schema = {"type": "string"}

    def __init__(self, memory: Memory):
        self._memory = memory

    async def run(self, content: str = None, category: str = None, metadata: dict = None, **kwargs) -> str:
        if content is None:
            content = kwargs.get("input", "")
        if not content:
            return "Error: No content provided"

        metadata = dict(metadata or {})
        if category:
            metadata["category"] = category

        item_id = self._memory.add(content, metadata=metadata)
        return f"Stored in memory (id: {item_id})"


def create_memory_tools(memory: Optional[Memory] = None):
    """Create memory tools for an Agent."""
    if memory is None:
        memory = Memory()

    return [
        MemorySearchTool(memory),
        MemoryAddTool(memory),
    ]


__all__ = ["MemorySearchTool", "MemoryAddTool", "create_memory_tools"]
