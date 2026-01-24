from abc import ABC, abstractmethod
from typing import List

from btflow.messages import Message


class BaseMemory(ABC):
    @abstractmethod
    def add(self, messages: List[Message]) -> None:
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str, k: int = 5) -> List[Message]:
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        raise NotImplementedError
