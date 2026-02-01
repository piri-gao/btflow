from __future__ import annotations

from typing import Any, Optional, Protocol, Sequence

from btflow.messages import Message


class ContextBuilderProtocol(Protocol):
    """Protocol for custom context builders."""

    def build(self, state: Any, tools_schema: Optional[dict] = None) -> Sequence[Message]:
        ...


__all__ = ["ContextBuilderProtocol"]
