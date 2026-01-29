"""
Memory Tools - Expose VectorMemory as Agent-callable tools.
"""
from typing import Optional
from btflow.tools import Tool
from btflow.memory.vector import VectorMemory


class MemorySearchTool(Tool):
    """Search for relevant memories."""
    
    name = "search_memory"
    description = "Search your long-term memory for relevant information. Returns past memories that are semantically similar to your query."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to search for in memory"
            },
            "k": {
                "type": "integer",
                "description": "Number of results to return (default: 3)"
            }
        },
        "required": ["query"]
    }
    output_schema = {"type": "string"}
    
    def __init__(self, memory: VectorMemory):
        self._memory = memory
    
    async def run(self, query: str = None, k: int = 3, **kwargs) -> str:
        if query is None:
            query = kwargs.get("input", "")
        if not query:
            return "Error: No query provided"
        
        items = self._memory.search_items(query, k=k)
        if not items:
            return "No relevant memories found."
        
        results = []
        for i, item in enumerate(items, 1):
            results.append(f"{i}. {item.content}")
        
        return "\n".join(results)


class MemoryAddTool(Tool):
    """Add new information to memory."""
    
    name = "add_memory"
    description = "Store important information in your long-term memory for future reference. Use this to remember facts, user preferences, or important context."
    input_schema = {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Information to remember"
            },
            "category": {
                "type": "string",
                "description": "Optional category (e.g., 'user_preference', 'fact', 'context')"
            }
        },
        "required": ["content"]
    }
    output_schema = {"type": "string"}
    
    def __init__(self, memory: VectorMemory):
        self._memory = memory
    
    async def run(self, content: str = None, category: str = None, **kwargs) -> str:
        if content is None:
            content = kwargs.get("input", "")
        if not content:
            return "Error: No content provided"
        
        metadata = {}
        if category:
            metadata["category"] = category
        
        item_id = self._memory.add_text(content, metadata=metadata)
        return f"Stored in memory (id: {item_id})"


def create_memory_tools(memory: Optional[VectorMemory] = None):
    """
    Create memory tools for an Agent.
    
    Args:
        memory: VectorMemory instance. If None, creates a new in-memory one.
        
    Returns:
        List of memory tools [MemorySearchTool, MemoryAddTool]
    """
    if memory is None:
        memory = VectorMemory()
    
    return [
        MemorySearchTool(memory),
        MemoryAddTool(memory),
    ]


__all__ = ["MemorySearchTool", "MemoryAddTool", "create_memory_tools"]
