from typing import List

from btflow.messages import Message
from btflow.messages.formatting import content_to_text
from btflow.memory.base import BaseMemory


class InMemoryHistory(BaseMemory):
    """Simple in-memory message store."""

    def __init__(self):
        self._messages: List[Message] = []

    def add(self, messages: List[Message]) -> None:
        self._messages.extend(messages)

    def search(self, query: str, k: int = 5) -> List[Message]:
        if not self._messages:
            return []

        if not query:
            return self._messages[-k:]

        q = query.lower()
        matched = [m for m in self._messages if q in content_to_text(m.content).lower()]
        if matched:
            return matched[-k:]

        return self._messages[-k:]

    def clear(self) -> None:
        self._messages.clear()
