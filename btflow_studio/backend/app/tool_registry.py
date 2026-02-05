from typing import List, Dict, Any, Optional, Type
from pydantic import BaseModel, Field
import inspect

from btflow.tools import (
    CalculatorTool,
    PythonREPLTool,
    FileReadTool,
    FileWriteTool,
    HTTPTool,
    DuckDuckGoSearchTool,
)
from btflow.memory import Memory
from btflow.memory.tools import MemorySearchTool, MemoryAddTool


class ToolMetadata(BaseModel):
    """Metadata for tools displayed in Studio."""
    id: str = Field(..., description="Unique tool type identifier")
    name: str = Field(..., description="Tool function name")
    label: str = Field(..., description="Display name")
    category: str = "Builtin"
    source: str = "builtin"
    description: str = ""
    available: bool = True
    error: Optional[str] = None
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)


def _docstring(obj: Any) -> str:
    return (inspect.getdoc(obj) or "").strip()


def _safe_instantiate(tool_cls: Type):
    try:
        if tool_cls in (MemorySearchTool, MemoryAddTool):
            return tool_cls(Memory()), None
        return tool_cls(), None
    except Exception as e:
        return None, str(e)


def _build_tool_meta(tool_cls: Type, category: str = "Builtin", source: str = "builtin") -> ToolMetadata:
    instance, error = _safe_instantiate(tool_cls)
    tool_name = getattr(tool_cls, "name", tool_cls.__name__)
    label = tool_cls.__name__
    description = _docstring(tool_cls)
    input_schema = getattr(instance, "input_schema", {}) if instance else {}
    output_schema = getattr(instance, "output_schema", {}) if instance else {}
    return ToolMetadata(
        id=tool_cls.__name__,
        name=tool_name,
        label=label,
        category=category,
        source=source,
        description=description,
        available=instance is not None,
        error=error,
        input_schema=input_schema,
        output_schema=output_schema,
    )


def get_builtin_tools() -> List[ToolMetadata]:
    tool_classes = [
        (CalculatorTool, "Builtin"),
        (PythonREPLTool, "Builtin"),
        (FileReadTool, "Builtin"),
        (FileWriteTool, "Builtin"),
        (HTTPTool, "Builtin"),
        (DuckDuckGoSearchTool, "Builtin"),
        (MemorySearchTool, "Memory"),
        (MemoryAddTool, "Memory"),
    ]
    return [_build_tool_meta(cls, category=category) for cls, category in tool_classes]


def get_tool_by_id(tool_id: str):
    mapping = {meta.id: meta for meta in get_builtin_tools()}
    return mapping.get(tool_id)


def get_tool_class_by_id(tool_id: str):
    tool_map = {
        CalculatorTool.__name__: CalculatorTool,
        PythonREPLTool.__name__: PythonREPLTool,
        FileReadTool.__name__: FileReadTool,
        FileWriteTool.__name__: FileWriteTool,
        HTTPTool.__name__: HTTPTool,
        DuckDuckGoSearchTool.__name__: DuckDuckGoSearchTool,
        MemorySearchTool.__name__: MemorySearchTool,
        MemoryAddTool.__name__: MemoryAddTool,
    }
    return tool_map.get(tool_id)


__all__ = ["ToolMetadata", "get_builtin_tools", "get_tool_by_id", "get_tool_class_by_id"]
