from __future__ import annotations

import uuid
from typing import Callable, Dict, List, Optional

from btflow.memory.record import MemoryRecord
from btflow.memory.retriever import (
    HybridRetriever,
    Retriever,
    SearchOptions,
    coerce_embedding,
    normalize_vector,
    simple_embedding,
)
from btflow.memory.ingest import load_text, chunk_text
from btflow.memory.store import InMemoryStore, JsonStore, SQLiteStore, MemoryStore
from btflow.messages import Message
from btflow.messages.formatting import content_to_text


class Memory:
    """Simple memory facade: store records and retrieve by query."""

    def __init__(
        self,
        store: Optional[MemoryStore] = None,
        retriever: Optional[Retriever] = None,
        embedder: Optional[Callable[[str], List[float]]] = None,
        embedding_dim: int = 64,
        persist_path: Optional[str] = None,
        autosave: bool = True,
        max_size: Optional[int] = None,
        normalize_embeddings: bool = True,
    ):
        if store is None:
            if persist_path:
                store = JsonStore(persist_path, max_size=max_size, autosave=autosave)
            else:
                store = InMemoryStore(max_size=max_size)
        if embedder is None:
            embedder = _build_embedding_fn(embedding_dim)

        self.store = store
        self.embedder = embedder
        self.normalize_embeddings = normalize_embeddings
        self.retriever = retriever or HybridRetriever(embedder=self.embedder, normalize_embeddings=normalize_embeddings)

    def add(self, text: str, metadata: Optional[Dict[str, object]] = None, embed: bool = True) -> str:
        record = MemoryRecord(
            id=str(uuid.uuid4()),
            text=text,
            metadata=dict(metadata or {}),
        )
        if embed and self.embedder is not None:
            vec = coerce_embedding(self.embedder(text))
            if vec is not None:
                record.embedding = normalize_vector(vec, normalize=self.normalize_embeddings)
        return self.store.add(record)

    def add_text(self, text: str, metadata: Optional[Dict[str, object]] = None, embed: bool = True) -> str:
        return self.add(text=text, metadata=metadata, embed=embed)

    def add_message(self, message: Message, embed: bool = True) -> str:
        metadata: Dict[str, object] = dict(message.metadata or {})
        metadata["role"] = message.role
        if message.name:
            metadata["name"] = message.name
        if message.tool:
            metadata["tool"] = message.tool
        if message.tool_calls:
            metadata["tool_calls"] = message.tool_calls
        content = content_to_text(message.content)
        return self.add(content, metadata=metadata, embed=embed)

    def ingest_text(
        self,
        text: str,
        chunk_size: int = 500,
        overlap: int = 0,
        metadata: Optional[Dict[str, object]] = None,
        embed: bool = True,
    ) -> List[str]:
        ids: List[str] = []
        chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        base_meta = dict(metadata or {})
        for i, chunk in enumerate(chunks):
            meta = dict(base_meta)
            meta.update({"chunk_index": i, "chunk_size": chunk_size, "overlap": overlap})
            ids.append(self.add(chunk, metadata=meta, embed=embed))
        return ids

    def ingest_file(
        self,
        path: str,
        chunk_size: int = 500,
        overlap: int = 0,
        metadata: Optional[Dict[str, object]] = None,
        embed: bool = True,
        encoding: str = "utf-8",
    ) -> List[str]:
        text = load_text(path, encoding=encoding)
        meta = dict(metadata or {})
        meta.setdefault("source", path)
        return self.ingest_text(text, chunk_size=chunk_size, overlap=overlap, metadata=meta, embed=embed)

    def search(self, query: str, options: Optional[SearchOptions] = None) -> List[MemoryRecord]:
        records = self.store.list()
        return self.retriever.search(query=query, records=records, options=options)

    def search_messages(self, query: str, options: Optional[SearchOptions] = None) -> List[Message]:
        results = self.search(query=query, options=options)
        messages: List[Message] = []
        for record in results:
            metadata = dict(record.metadata or {})
            role = str(metadata.get("role", "system"))
            name = metadata.get("name")
            tool = metadata.get("tool")
            tool_calls = metadata.get("tool_calls")
            messages.append(
                Message(
                    role=role,
                    content=record.text,
                    name=name,
                    tool=tool,
                    tool_calls=tool_calls,
                    metadata=metadata,
                )
            )
        return messages

    def get(self, record_id: str) -> Optional[MemoryRecord]:
        return self.store.get(record_id)

    def delete(self, record_id: str) -> bool:
        return self.store.delete(record_id)

    def clear(self) -> None:
        self.store.clear()

    def save(self) -> None:
        if hasattr(self.store, "save"):
            self.store.save()  # type: ignore[attr-defined]

    def __len__(self) -> int:
        return len(self.store)

    def as_tools(self):
        from btflow.memory.tools import MemorySearchTool, MemoryAddTool
        return [MemorySearchTool(self), MemoryAddTool(self)]


def _build_embedding_fn(embedding_dim: int):
    def _embed(text: str):
        return simple_embedding(text, embedding_dim)
    return _embed


__all__ = ["Memory"]
