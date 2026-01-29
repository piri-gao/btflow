from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, List, Dict, AsyncIterator
from btflow.messages import Message


@dataclass
class MessageChunk:
    text: str = ""
    tool_calls: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None
    raw: Optional[Any] = None


class LLMProvider(ABC):
    @abstractmethod
    async def generate_text(
        self,
        prompt: Any,
        model: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.95,
        top_k: int = 40,
        timeout: float = 60.0,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        strict_tools: bool = False,
        **kwargs
    ) -> Message:
        raise NotImplementedError

    async def generate_stream(
        self,
        prompt: Any,
        model: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.95,
        top_k: int = 40,
        timeout: float = 60.0,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        strict_tools: bool = False,
        **kwargs
    ) -> AsyncIterator[MessageChunk]:
        raise NotImplementedError
