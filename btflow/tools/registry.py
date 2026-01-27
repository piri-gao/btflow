from typing import Callable, Dict, Iterable, Optional, Any

from btflow.tools.base import Tool, ToolResult, ToolError


class FunctionTool(Tool):
    """Wrap a simple callable as a Tool."""
    def __init__(
        self,
        name: str,
        description: str,
        fn: Callable[[Any], Any],
        input_schema: Optional[dict] = None,
        output_schema: Optional[dict] = None,
    ):
        self.name = name
        self.description = description
        self._fn = fn
        if input_schema is not None:
            self.input_schema = input_schema
        if output_schema is not None:
            self.output_schema = output_schema

    def run(self, *args, **kwargs) -> Any:
        return self._fn(*args, **kwargs)


class ToolRegistry:
    """Registry for tools to simplify construction and reuse."""
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        self._tools[tool.name.lower()] = tool
        return tool

    def register_function(
        self,
        name: str,
        description: str,
        fn: Callable[[Any], Any],
        input_schema: Optional[dict] = None,
        output_schema: Optional[dict] = None,
    ) -> Tool:
        tool = FunctionTool(
            name=name,
            description=description,
            fn=fn,
            input_schema=input_schema,
            output_schema=output_schema,
        )
        return self.register(tool)

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name.lower())

    def list(self) -> Iterable[Tool]:
        return list(self._tools.values())

    def remove(self, name: str) -> Optional[Tool]:
        return self._tools.pop(name.lower(), None)

    def clear(self) -> None:
        self._tools.clear()


__all__ = ["ToolRegistry", "FunctionTool", "ToolResult", "ToolError"]
