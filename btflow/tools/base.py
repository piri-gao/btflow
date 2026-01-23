from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ToolSpec:
    """Tool metadata used for prompt building and validation."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }


@dataclass
class ToolResult:
    """Normalized tool execution result."""
    ok: bool
    output: Any = None
    error: Optional[str] = None
    retryable: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "output": self.output,
            "error": self.error,
            "retryable": self.retryable,
        }


class ToolError(Exception):
    """Structured tool failure for classification and retry policies."""
    def __init__(self, message: str, code: str = "tool_error", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class Tool(ABC):
    """
    Tool base class for agent patterns.

    Subclass this and implement the `run` method to create custom tools.
    """
    name: str = "unnamed_tool"
    description: str = "No description provided"
    input_schema: Dict[str, Any] = {"type": "string", "description": "Tool input string"}
    output_schema: Dict[str, Any] = {"type": "string", "description": "Tool output string"}

    @abstractmethod
    def run(self, input: Any) -> Any:
        """
        Execute the tool with given input.

        Args:
            input: The input string from the LLM's action

        Returns:
            Result string to be used as observation
        """
        pass

    def spec(self) -> ToolSpec:
        """Return a normalized tool spec for prompts and UIs."""
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
            output_schema=self.output_schema,
        )
