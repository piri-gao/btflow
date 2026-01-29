from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


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

    def as_node(
        self,
        name: Optional[str] = None,
        input_map: Optional[Dict[str, Any]] = None,
        output_key: Optional[str] = None,
        **kwargs
    ):
        """
        Wrap this tool into a ToolNode for use in a behavior tree.
        """
        from btflow.tools.node import ToolNode
        return ToolNode(
            name=name or self.name,
            tool=self,
            input_map=input_map,
            output_key=output_key,
            **kwargs
        )

    def _normalize_parameters(self) -> Dict[str, Any]:
        """Normalize input schema into a function-calling compatible JSON Schema."""
        schema = self.input_schema or {}
        schema_type = schema.get("type")
        if schema_type == "object":
            normalized = dict(schema)
            normalized.setdefault("type", "object")
            normalized.setdefault("properties", {})
            return normalized
        if schema_type is None and "properties" in schema:
            normalized = dict(schema)
            normalized.setdefault("type", "object")
            return normalized
        # Wrap non-object input as a single "input" field
        return {
            "type": "object",
            "properties": {
                "input": dict(schema) if schema else {"type": "string"}
            },
            "required": ["input"],
        }

    def _normalize_output_schema(self) -> Dict[str, Any]:
        """Normalize output schema into an object-shaped JSON Schema."""
        schema = self.output_schema or {}
        schema_type = schema.get("type")
        if schema_type == "object":
            normalized = dict(schema)
            normalized.setdefault("type", "object")
            normalized.setdefault("properties", {})
            return normalized
        if schema_type is None and "properties" in schema:
            normalized = dict(schema)
            normalized.setdefault("type", "object")
            return normalized
        # Wrap non-object output as a single "output" field
        return {
            "type": "object",
            "properties": {
                "output": dict(schema) if schema else {"type": "string"}
            },
            "required": ["output"],
        }

    def to_openai(self) -> Dict[str, Any]:
        """OpenAI-style function schema (name/description/parameters)."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self._normalize_parameters(),
            "returns": self._normalize_output_schema(),
        }

    def spec(self) -> Dict[str, Any]:
        """Return a normalized tool spec for prompts and UIs."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "parameters": self._normalize_parameters(),
            "returns": self._normalize_output_schema(),
        }
