import inspect
from typing import Callable, Any, Optional

from btflow.tools.base import Tool


def _get_metadata(func: Callable, name: Optional[str] = None, description: Optional[str] = None):
    final_name = name or func.__name__
    final_desc = description or (func.__doc__ or "").strip() or ""
    return final_name, final_desc


class FunctionTool(Tool):
    """Wrap a simple callable as a Tool."""
    def __init__(
        self,
        name: str,
        description: str,
        fn: Callable[..., Any],
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


def tool(
    _func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    input_schema: Optional[dict] = None,
    output_schema: Optional[dict] = None,
):
    """
    Decorator to wrap a function into a Tool instance.
    Usage:
        @tool
        def my_tool(input): ...

        @tool(name="custom")
        def my_tool(input): ...
    """
    def decorator(func: Callable):
        tool_name, tool_desc = _get_metadata(func, name, description)
        return FunctionTool(
            name=tool_name,
            description=tool_desc,
            fn=func,
            input_schema=input_schema,
            output_schema=output_schema,
        )

    if _func is None:
        return decorator
    return decorator(_func)


__all__ = ["tool", "FunctionTool"]
