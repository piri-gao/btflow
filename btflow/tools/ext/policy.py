from abc import ABC, abstractmethod
from typing import Any, List, Optional

from btflow.tools.base import Tool


class ToolSelectionPolicy(ABC):
    @abstractmethod
    def select_tools(self, state: Any, available_tools: List[Tool]) -> List[Tool]:
        """Return the tools that should be visible to the LLM."""
        raise NotImplementedError

    def validate_call(self, state: Any, tool_name: str, tool_input: Any) -> Optional[str]:
        """Return an error string to block execution, or None to allow."""
        return None


class AllowAllToolPolicy(ToolSelectionPolicy):
    def select_tools(self, state: Any, available_tools: List[Tool]) -> List[Tool]:
        return available_tools


__all__ = ["ToolSelectionPolicy", "AllowAllToolPolicy"]
