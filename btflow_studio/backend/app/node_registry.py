from typing import List, Dict, Any, Optional, Type, Callable, Union
from pydantic import BaseModel, Field
import inspect

from btflow import Sequence, Selector, Parallel


def _docstring(obj: Any) -> str:
    return (inspect.getdoc(obj) or "").strip()


def _resolve_description(explicit: Optional[str], target: Any = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    if target is None:
        return ""
    return _docstring(target)

class NodeMetadata(BaseModel):
    """Metadata for a node type to be rendered in the UI."""
    model_config = {"arbitrary_types_allowed": True}

    id: str = Field(..., description="Unique node type identifier (matches NodeDefinition.type)")
    label: str
    category: str = "Common"
    icon: str = "🧩"
    description: str = ""
    
    # I/O Contracts
    inputs: List[Dict[str, Any]] = Field(default_factory=list, description="Input ports for binding")
    outputs: List[Dict[str, Any]] = Field(default_factory=list, description="Output ports for binding")
    
    # Configuration Schema (for UI form generation)
    # Format: { "param_name": { "type": "select", "options": [...], ... } }
    config_schema: Dict[str, Any] = Field(default_factory=dict)
    
    # Runtime binding
    node_class: Optional[Union[Type, Callable]] = Field(None, exclude=True)

class NodeRegistry:
    def __init__(self):
        self._nodes: Dict[str, NodeMetadata] = {}
        self._class_map: Dict[str, Type] = {}
    
    def register(self, 
                 cls: Optional[Type] = None, 
                 *,
                 id: Optional[str] = None,
                 label: Optional[str] = None,
                 category: str = "Custom",
                 icon: str = "🧩",
                 description: str = "",
                 inputs: List[str] = None,
                 outputs: List[str] = None,
                 config_schema: Dict[str, Any] = None):
        """
        Decorator to register a node class with metadata.
        
        Usage:
            @registry.register(label="My Node", category="Logic")
            class MyNode(Behaviour): ...
        """
        def _decorator(target_cls):
            nonlocal id, label, description
            
            node_id = id or target_cls.__name__
            node_label = label or node_id
            node_desc = _resolve_description(description, target_cls)
            
            meta = NodeMetadata(
                id=node_id,
                label=node_label,
                category=category,
                icon=icon,
                description=node_desc,
                inputs=inputs or [],
                outputs=outputs or [],
                config_schema=config_schema or {},
                node_class=target_cls
            )
            
            self._nodes[node_id] = meta
            self._class_map[node_id] = target_cls
            return target_cls

        if cls is None:
            return _decorator
        return _decorator(cls)
    
    def register_metadata(self, meta: NodeMetadata):
        """Register metadata without a python class (for virtual nodes)."""
        if (not meta.description) and meta.node_class is not None:
            meta.description = _docstring(meta.node_class)
        self._nodes[meta.id] = meta
        # Also add to class map if node_class is provided (e.g., for lambda factories)
        if meta.node_class is not None:
            self._class_map[meta.id] = meta.node_class

    def get(self, node_id: str) -> Optional[NodeMetadata]:
        return self._nodes.get(node_id)
    
    def get_all(self) -> List[NodeMetadata]:
        return list(self._nodes.values())
    
    def get_class(self, node_id: str) -> Optional[Type]:
        return self._class_map.get(node_id)

# Global Registry Instance
node_registry = NodeRegistry()

# === Register Builtin Nodes ===

# 1. Composites
node_registry.register_metadata(NodeMetadata(
    id="Sequence", label="Sequence", category="Control Flow", icon="➡️",
    config_schema={"memory": {"type": "boolean", "default": False}},
    node_class=Sequence
))

node_registry.register_metadata(NodeMetadata(
    id="Selector", label="Selector", category="Control Flow", icon="❓",
    config_schema={"memory": {"type": "boolean", "default": False}},
    node_class=Selector
))

node_registry.register_metadata(NodeMetadata(
    id="Parallel", label="Parallel", category="Control Flow", icon="🔀",
    config_schema={
        "policy": {
            "type": "select", 
            "options": ["SuccessOnAll", "SuccessOnOne", "FailureOnAll", "FailureOnOne"],
            "default": "SuccessOnAll"
        }
    },
    node_class=Parallel
))

# 2. Debug & Action Nodes
from btflow.nodes import Log
from btflow.nodes import Wait
from btflow.nodes.builtin.action import SetTask

node_registry.register(
    Log,
    id="Log",
    label="Log Message",
    category="Debug",
    icon="📝",
    config_schema={
        "message": {
            "type": "text",
            "default": "",
            "label": "Message"
        }
    }
)

node_registry.register(
    Wait,
    id="Wait",
    label="Wait",
    category="Action",
    icon="⏳",
    config_schema={
        "duration": {
            "type": "number",
            "default": 1.0,
            "label": "Duration (s)"
        }
    }
)

node_registry.register(
    SetTask,
    id="SetTask",
    label="Set Agent Task",
    category="Action",
    icon="🎯",
    outputs=[
        {"name": "task", "type": "str", "default": ""}
    ],
    config_schema={
        "task_content": {
            "type": "textarea",
            "default": "",
            "label": "Task Content"
        }
    }
)
# 3. Import and Register Advanced Patterns & Tools
from btflow.core.composites import LoopUntilSuccess
from btflow.nodes import ReActLLMNode, ToolExecutor, IsFinalAnswer
from btflow.nodes import SelfRefineLLMNode, IsGoodEnough
from btflow.tools import CalculatorTool
from btflow.tools.node import ToolNode

def _tool_description(tool_cls: Type) -> str:
    return _resolve_description(None, tool_cls)


def _register_tool_meta(tool_cls: Type, node_id: str, label: str, icon: str):
    node_registry.register_metadata(NodeMetadata(
        id=node_id,
        label=label,
        category="Tools",
        icon=icon,
        description=_tool_description(tool_cls),
        inputs=[{"name": "input", "type": "any", "default": ""}],
        outputs=[{"name": "output", "type": "any", "default": None}],
        node_class=lambda **kwargs: ToolNode(name=kwargs.get("name", label), tool=tool_cls())
    ))


# Tools
_register_tool_meta(CalculatorTool, "CalculatorTool", "Calculator", "🧮")

# Generic ToolNode (deterministic tool execution)
node_registry.register(
    ToolNode,
    id="ToolNode",
    label="Tool Node",
    category="Tools",
    icon="🧰",
    inputs=[{"name": "input", "type": "any", "default": ""}],
    outputs=[{"name": "output", "type": "any", "default": None}],
    config_schema={
        "tool_id": {
            "type": "select",
            "label": "Tool",
            "source": "tools",
            "default": "",
        },
        "execute": {
            "type": "boolean",
            "label": "Execute",
            "default": True,
        },
        "strict_output_validation": {
            "type": "boolean",
            "label": "Strict Output",
            "default": False,
        },
        "memory_id": {
            "type": "text",
            "label": "Memory ID",
            "default": "default",
        },
    },
)

# LoopUntilSuccess
node_registry.register_metadata(NodeMetadata(
    id="LoopUntilSuccess", label="Loop Until Success", category="Control Flow", icon="🔄",
    config_schema={
        "max_iterations": {"type": "number", "default": 10}
    },
    node_class=LoopUntilSuccess
))
node_registry._class_map["LoopUntilSuccess"] = LoopUntilSuccess

# ReAct Nodes
node_registry.register(
    ReActLLMNode,
    id="ReActLLMNode", label="ReAct LLM", category="Agent (ReAct)", icon="🤖",
    inputs=[
        {"name": "messages", "type": "list", "default": []},
        {"name": "task", "type": "str", "default": ""},
        {"name": "tools_desc", "type": "str", "default": ""},
        {"name": "tools_schema", "type": "list", "default": []},
    ],
    outputs=[
        {"name": "messages", "type": "list", "default": []},
        {"name": "round", "type": "int", "default": 0},
        {"name": "streaming_output", "type": "str", "default": ""},
    ],
    config_schema={
        "model": {"type": "text", "default": "gemini-2.5-flash"},
        "system_prompt": {"type": "textarea", "default": ""},
        "memory_id": {"type": "text", "default": "default"},
        "memory_top_k": {"type": "number", "default": 5}
    }
)


node_registry.register(
    ToolExecutor,
    id="ToolExecutor", label="Tool Executor", category="Agent (ReAct)", icon="🛠️",
    inputs=[
        {"name": "messages", "type": "list", "default": []},
    ],
    outputs=[
        {"name": "messages", "type": "list", "default": []},
        {"name": "tools_desc", "type": "str", "default": ""},
        {"name": "tools_schema", "type": "list", "default": []},
    ],
    config_schema={
        "tools": {
            "type": "multiselect",
            "label": "Tools",
            "source": "tools",
            "default": []
        },
        "memory_id": {"type": "text", "default": "default"}
    }
)

node_registry.register(
    IsFinalAnswer,
    id="IsFinalAnswer", label="Is Final Answer?", category="Agent (ReAct)", icon="✅",
    inputs=[
        {"name": "messages", "type": "list", "default": []},
        {"name": "round", "type": "int", "default": 0},
    ],
    outputs=[
        {"name": "final_answer", "type": "str", "default": ""},
    ],
    config_schema={
        "max_rounds": {"type": "number", "default": 10}
    }
)

# Reflexion Nodes
node_registry.register(
    SelfRefineLLMNode,
    id="SelfRefineLLMNode", label="Self-Refine LLM", category="Agent (Reflexion)", icon="🪞",
    inputs=[
        {"name": "task", "type": "str", "default": ""},
        {"name": "messages", "type": "list", "default": []},
        {"name": "round", "type": "int", "default": 0},
        {"name": "answer", "type": "str", "default": ""},
        {"name": "score", "type": "float", "default": 0.0},
        {"name": "reflection", "type": "str", "default": ""},
    ],
    outputs=[
        {"name": "messages", "type": "list", "default": []},
        {"name": "answer", "type": "str", "default": ""},
        {"name": "answer_history", "type": "list", "default": []},
        {"name": "score", "type": "float", "default": 0.0},
        {"name": "score_history", "type": "list", "default": []},
        {"name": "reflection", "type": "str", "default": ""},
        {"name": "reflection_history", "type": "list", "default": []},
        {"name": "round", "type": "int", "default": 0},
        {"name": "is_complete", "type": "bool", "default": False},
        {"name": "streaming_output", "type": "str", "default": ""},
    ],
    config_schema={
        "model": {"type": "text", "default": "gemini-2.5-flash"},
        "memory_id": {"type": "text", "default": "default"},
        "memory_top_k": {"type": "number", "default": 5}
    }
)

node_registry.register(
    IsGoodEnough,
    id="IsGoodEnough", label="Is Good Enough?", category="Agent (Reflexion)", icon="⚖️",
    inputs=[
        {"name": "score", "type": "float", "default": 0.0},
        {"name": "round", "type": "int", "default": 0},
    ],
    outputs=[
        {"name": "is_complete", "type": "bool", "default": False},
    ],
    config_schema={
        "threshold": {"type": "number", "default": 8.0},
        "max_rounds": {"type": "number", "default": 5}
    }
)
