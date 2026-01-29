"""
Vector Memory - Semantic search using embeddings.

Provides long-term memory with vector similarity search.
Supports pluggable embedding functions and storage backends.
"""
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from btflow.memory.base import BaseMemory
from btflow.messages import Message


@dataclass
class MemoryItem:
    """A single memory entry with embedding."""
    id: str
    content: str
    embedding: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def simple_embedding(text: str, dim: int = 64) -> List[float]:
    """
    Simple bag-of-chars embedding (no external dependencies).
    
    NOT for production - use a real embedding model for better results.
    This is just for zero-dependency demo purposes.
    """
    # Create a simple hash-based embedding
    vec = [0.0] * dim
    for i, char in enumerate(text.lower()):
        idx = ord(char) % dim
        vec[idx] += 1.0 / (1 + i * 0.01)  # Position-weighted contribution
    
    # Normalize
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


class VectorMemory(BaseMemory):
    """
    Vector-based memory with semantic search.
    
    Features:
        - Pluggable embedding function (default: simple bag-of-chars)
        - Cosine similarity search
        - Optional file persistence
        - Metadata support
    
    Example:
        memory = VectorMemory()
        memory.add_text("Python is a programming language")
        memory.add_text("Machine learning models require data")
        results = memory.search("coding language", k=1)
    """
    
    def __init__(
        self,
        embedding_fn: Optional[Callable[[str], List[float]]] = None,
        persist_path: Optional[str] = None,
        embedding_dim: int = 64,
    ):
        """
        Initialize vector memory.
        
        Args:
            embedding_fn: Custom embedding function (text -> vector).
                          If None, uses simple_embedding.
            persist_path: Optional file path for persistence (.json).
            embedding_dim: Dimension for simple_embedding (ignored if custom fn).
        """
        self._embedding_fn = embedding_fn or (lambda t: simple_embedding(t, embedding_dim))
        self._persist_path = Path(persist_path) if persist_path else None
        self._items: Dict[str, MemoryItem] = {}
        self._counter = 0
        
        # Load existing data if persist path exists
        if self._persist_path and self._persist_path.exists():
            self._load()
    
    def add_text(
        self, 
        content: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add a text entry to memory.
        
        Args:
            content: Text content to store
            metadata: Optional metadata dict
            
        Returns:
            The ID of the stored memory item
        """
        self._counter += 1
        item_id = f"mem_{self._counter}"
        
        embedding = self._embedding_fn(content)
        item = MemoryItem(
            id=item_id,
            content=content,
            embedding=embedding,
            metadata=metadata or {},
        )
        self._items[item_id] = item
        
        if self._persist_path:
            self._save()
        
        return item_id
    
    def add(self, messages: List[Message]) -> None:
        """Add messages to memory (BaseMemory interface)."""
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            self.add_text(content, metadata={"role": msg.role})
    
    def search(self, query: str, k: int = 5) -> List[Message]:
        """
        Search for similar memories (BaseMemory interface).
        
        Returns Messages for compatibility with existing code.
        """
        items = self.search_items(query, k)
        return [
            Message(
                role=item.metadata.get("role", "system"),
                content=item.content
            )
            for item in items
        ]
    
    def search_items(self, query: str, k: int = 5) -> List[MemoryItem]:
        """
        Search for similar memories.
        
        Args:
            query: Search query text
            k: Number of results to return
            
        Returns:
            List of MemoryItem sorted by similarity (highest first)
        """
        if not self._items:
            return []
        
        query_embedding = self._embedding_fn(query)
        
        # Calculate similarities
        scored = []
        for item in self._items.values():
            sim = cosine_similarity(query_embedding, item.embedding)
            scored.append((sim, item))
        
        # Sort by similarity (descending)
        scored.sort(key=lambda x: x[0], reverse=True)
        
        return [item for _, item in scored[:k]]
    
    def get(self, item_id: str) -> Optional[MemoryItem]:
        """Get a specific memory item by ID."""
        return self._items.get(item_id)
    
    def clear(self) -> None:
        """Clear all memories."""
        self._items.clear()
        self._counter = 0
        if self._persist_path:
            self._save()
    
    def _save(self) -> None:
        """Save memories to file."""
        if not self._persist_path:
            return
        
        data = {
            "counter": self._counter,
            "items": [
                {
                    "id": item.id,
                    "content": item.content,
                    "embedding": item.embedding,
                    "metadata": item.metadata,
                    "created_at": item.created_at,
                }
                for item in self._items.values()
            ]
        }
        
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._persist_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _load(self) -> None:
        """Load memories from file."""
        if not self._persist_path or not self._persist_path.exists():
            return
        
        with open(self._persist_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        self._counter = data.get("counter", 0)
        for item_data in data.get("items", []):
            item = MemoryItem(
                id=item_data["id"],
                content=item_data["content"],
                embedding=item_data["embedding"],
                metadata=item_data.get("metadata", {}),
                created_at=item_data.get("created_at", ""),
            )
            self._items[item.id] = item
    
    def __len__(self) -> int:
        return len(self._items)
    
    def __repr__(self) -> str:
        return f"VectorMemory(items={len(self._items)})"
