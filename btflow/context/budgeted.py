from __future__ import annotations

from typing import Any, List, Optional, Sequence

from btflow.context.base import ContextBuilderProtocol
from btflow.context.builder import ContextBuilder
from btflow.messages import Message, system
from btflow.messages.formatting import message_to_text
from btflow.memory import Memory, SearchOptions


class SimpleTokenCounter:
    """Approximate token counter based on character length."""

    def __init__(self, chars_per_token: int = 4):
        self.chars_per_token = max(1, int(chars_per_token))

    def count_message(self, message: Message) -> int:
        text = message_to_text(message)
        return max(1, len(text) // self.chars_per_token)

    def count_messages(self, messages: Sequence[Message]) -> int:
        return sum(self.count_message(m) for m in messages)


class BudgetedContextBuilder(ContextBuilder):
    """ContextBuilder with a token budget and simple truncation strategy."""

    def __init__(
        self,
        system_prompt: Optional[str] = None,
        tools_desc: Optional[str] = None,
        memory: Optional[Memory] = None,
        memory_top_k: int = 5,
        max_messages: Optional[int] = None,
        max_tokens: int = 4096,
        truncate_order: Sequence[str] = ("memory", "messages"),
        include_tools: bool = True,
        include_memory: bool = True,
        token_counter: Optional[object] = None,
        chars_per_token: int = 4,
    ):
        super().__init__(
            system_prompt=system_prompt,
            tools_desc=tools_desc,
            memory=memory,
            memory_top_k=memory_top_k,
            max_messages=max_messages,
        )
        self.max_tokens = max_tokens
        self.truncate_order = tuple(truncate_order)
        self.include_tools = include_tools
        self.include_memory = include_memory
        self.token_counter = token_counter or SimpleTokenCounter(chars_per_token=chars_per_token)

    def build(self, state: Any, tools_schema: Optional[dict] = None) -> List[Message]:
        user_messages = self._extract_user_messages(state)
        segments = self._build_segments(user_messages)
        segments = self._truncate_segments(segments)
        messages = self._render_segments(segments)

        if self.max_messages is not None and len(messages) > self.max_messages:
            messages = messages[-self.max_messages :]

        return messages

    def _extract_user_messages(self, state: Any) -> List[Message]:
        if isinstance(state, list):
            return list(state)
        if hasattr(state, "messages"):
            return list(getattr(state, "messages") or [])
        return []

    def _build_segments(self, user_messages: List[Message]) -> List[dict]:
        segments: List[dict] = []

        if self.system_prompt:
            segments.append({
                "name": "system",
                "messages": [system(self.system_prompt)],
                "trim_from_start": False,
                "required": True,
            })

        if self.tools_desc and self.include_tools:
            segments.append({
                "name": "tools",
                "messages": [system(f"Available tools:\n{self.tools_desc}")],
                "trim_from_start": False,
                "required": True,
            })

        if self.memory is not None and self.include_memory:
            query = message_to_text(user_messages[-1]) if user_messages else ""
            memory_messages = self.memory.search_messages(
                query=query,
                options=SearchOptions(k=self.memory_top_k),
            )
            if memory_messages:
                segments.append({
                    "name": "memory",
                    "messages": list(memory_messages),
                    # Keep top-ranked memory items; trim least relevant from end.
                    "trim_from_start": False,
                    "required": False,
                })

        segments.append({
            "name": "messages",
            "messages": list(user_messages),
            # Keep recent messages; trim oldest from start.
            "trim_from_start": True,
            "required": True,
        })

        return segments

    def _truncate_segments(self, segments: List[dict]) -> List[dict]:
        total_tokens = self._count_messages([m for seg in segments for m in seg["messages"]])
        if total_tokens <= self.max_tokens:
            return segments

        by_name = {seg["name"]: seg for seg in segments}
        for name in self.truncate_order:
            segment = by_name.get(name)
            if segment is None or not segment["messages"]:
                continue
            while segment["messages"] and total_tokens > self.max_tokens:
                msg = segment["messages"].pop(0 if segment["trim_from_start"] else -1)
                total_tokens -= self._count_message(msg)
            if total_tokens <= self.max_tokens:
                break

        return segments

    def _render_segments(self, segments: List[dict]) -> List[Message]:
        messages: List[Message] = []
        for seg in segments:
            messages.extend(seg["messages"])
        return messages

    def _count_message(self, message: Message) -> int:
        counter = self.token_counter
        if hasattr(counter, "count_message"):
            return counter.count_message(message)
        if callable(counter):
            return int(counter([message]))
        return 0

    def _count_messages(self, messages: Sequence[Message]) -> int:
        counter = self.token_counter
        if hasattr(counter, "count_messages"):
            return counter.count_messages(messages)
        if callable(counter):
            return int(counter(messages))
        return 0


__all__ = ["BudgetedContextBuilder", "SimpleTokenCounter"]
