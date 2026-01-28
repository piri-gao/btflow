from typing import List, Optional, Protocol, Sequence, Any

from btflow.messages import Message, system
from btflow.memory import BaseMemory


class ContextBuilderProtocol(Protocol):
    """Protocol for custom context builders."""

    def build(
        self,
        state: Any,
        tools_schema: Optional[dict] = None,
    ) -> Sequence[Message]:
        ...


class ContextBuilder:
    """Build a message list from system prompt, memory, tools, and user input."""

    def __init__(
        self,
        system_prompt: Optional[str] = None,
        tools_desc: Optional[str] = None,
        memory: Optional[BaseMemory] = None,
        memory_top_k: int = 5,
        max_messages: Optional[int] = None,
    ):
        self.system_prompt = system_prompt
        self.tools_desc = tools_desc
        self.memory = memory
        self.memory_top_k = memory_top_k
        self.max_messages = max_messages

    def build(
        self,
        state: Any,
        tools_schema: Optional[dict] = None,
    ) -> List[Message]:
        messages: List[Message] = []

        user_messages: List[Message]
        if isinstance(state, list):
            user_messages = state
        elif hasattr(state, "messages"):
            user_messages = list(getattr(state, "messages") or [])
        else:
            user_messages = []

        if self.system_prompt:
            messages.append(system(self.system_prompt))

        if self.tools_desc:
            messages.append(system(f"Available tools:\n{self.tools_desc}"))

        if self.memory is not None:
            query = user_messages[-1].content if user_messages else ""
            memory_messages = self.memory.search(query=query, k=self.memory_top_k)
            messages.extend(memory_messages)

        messages.extend(user_messages)

        if self.max_messages is not None and len(messages) > self.max_messages:
            messages = messages[-self.max_messages:]

        return messages
