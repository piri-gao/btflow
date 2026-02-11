"""btflow memory module - minimal triad (Record / Store / Retriever) with a Memory facade."""

from btflow.memory.record import MemoryRecord
from btflow.memory.store import MemoryStore, InMemoryStore, JsonStore, SQLiteStore
from btflow.memory.ingest import load_text, chunk_text
from btflow.memory.retriever import Retriever, HybridRetriever, SearchOptions
from btflow.memory.memory import Memory
from btflow.memory.tools import MemorySearchTool, MemoryAddTool, create_memory_tools
from btflow.memory.embedders import GeminiEmbedder, OpenAIEmbedder, resolve_embedder

__all__ = [
    "MemoryRecord",
    "SearchOptions",
    "MemoryStore",
    "InMemoryStore",
    "JsonStore",
    "SQLiteStore",
    "load_text",
    "chunk_text",
    "Retriever",
    "HybridRetriever",
    "Memory",
    "MemorySearchTool",
    "MemoryAddTool",
    "create_memory_tools",
    "GeminiEmbedder",
    "OpenAIEmbedder",
    "resolve_embedder",
]
