from typing import List

from btflow.messages import Message
from btflow.memory.base import BaseMemory


class WindowBufferMemory(BaseMemory):
    """Keep only the most recent N messages."""

    def __init__(self, max_size: int = 20):
        self.max_size = max_size
        self._messages: List[Message] = []

    def add(self, messages: List[Message]) -> None:
        self._messages.extend(messages)
        if len(self._messages) > self.max_size:
            self._messages = self._messages[-self.max_size:]

    def search(self, query: str, k: int = 5) -> List[Message]:
        if not self._messages:
            return []

        if not query:
            return self._messages[-k:]

        matched = [m for m in self._messages if query.lower() in m.content.lower()]
        if matched:
            return matched[-k:]

        return self._messages[-k:]

    def clear(self) -> None:
        self._messages.clear()
