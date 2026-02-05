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

# 3. Import and Register Advanced Patterns & Tools
from btflow.core.composites import LoopUntilSuccess
from btflow.nodes import AgentLLMNode, ToolExecutor, ParserNode, ConditionNode
from btflow.tools import CalculatorTool
from btflow.tools import ToolNode

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

node_registry.register(
    AgentLLMNode,
    id="AgentLLMNode", label="Agent LLM", category="Agent", icon="🤖",
    inputs=[
        {"name": "messages", "type": "list", "default": []},
        {"name": "task", "type": "str", "default": ""},
        {"name": "tools_desc", "type": "str", "default": ""},
        {"name": "tools_schema", "type": "list", "default": []},
    ],
    outputs=[
        {"name": "messages", "type": "list", "default": []},
        {"name": "rounds", "type": "int", "default": 0},
        {"name": "streaming_output", "type": "str", "default": ""},
    ],
    config_schema={
        "model": {"type": "text", "default": "gemini-2.5-flash"},
        "system_prompt": {"type": "textarea", "default": ""},
        "memory_id": {"type": "text", "default": "default"},
        "memory_top_k": {"type": "number", "default": 5},
        "structured_tool_calls": {"type": "boolean", "default": True},
        "strict_tool_calls": {"type": "boolean", "default": False},
        "stream": {"type": "boolean", "default": False},
    }
)


node_registry.register(
    ToolExecutor,
    id="ToolExecutor", label="Tool Executor", category="Agent", icon="🛠️",
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
    ParserNode,
    id="ParserNode", label="Parser", category="Agent", icon="🧩",
    inputs=[
        {"name": "messages", "type": "list", "default": []},
    ],
    outputs=[
        {"name": "final_answer", "type": "str", "default": ""},
        {"name": "answer", "type": "str", "default": ""},
        {"name": "answer_history", "type": "list", "default": []},
        {"name": "score", "type": "float", "default": 0.0},
        {"name": "score_history", "type": "list", "default": []},
        {"name": "reflection", "type": "str", "default": ""},
        {"name": "reflection_history", "type": "list", "default": []},
        {"name": "actions", "type": "list", "default": []},
        {"name": "parsed", "type": "str", "default": ""},
    ],
    config_schema={
        "preset": {
            "type": "select",
            "options": ["final_answer", "score", "action", "custom"],
            "labelMap": {
                "final_answer": "提取 Final Answer",
                "score": "提取 Score",
                "action": "提取 Action/Input",
                "custom": "自定义正则",
            },
            "default": "final_answer",
        },
        "custom_pattern": {
            "type": "text",
            "showWhen": {"preset": "custom"},
            "placeholder": r"Score:\\s*([0-9.]+)",
        },
    }
)

node_registry.register(
    ConditionNode,
    id="ConditionNode", label="Condition", category="Agent", icon="⚖️",
    inputs=[
        {"name": "messages", "type": "list", "default": []},
        {"name": "final_answer", "type": "str", "default": ""},
        {"name": "score", "type": "float", "default": 0.0},
        {"name": "rounds", "type": "int", "default": 0},
    ],
    outputs=[
        {"name": "passed", "type": "bool", "default": False},
        {"name": "is_complete", "type": "bool", "default": False},
    ],
    config_schema={
        "preset": {
            "type": "select",
            "options": ["score_gte", "has_final_answer", "max_rounds"],
            "labelMap": {
                "score_gte": "分数达标",
                "has_final_answer": "Final Answer 存在",
                "max_rounds": "达到最大轮数",
            },
            "default": "score_gte",
        },
        "threshold": {
            "type": "number",
            "default": 8.0,
            "showWhen": {"preset": "score_gte"},
        },
        "max_rounds": {
            "type": "number",
            "default": 10,
            "showWhen": {"preset": "max_rounds"},
        },
    }
)
