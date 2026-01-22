from typing import List, Dict, Any, Optional, Type, Callable, Union
from pydantic import BaseModel, Field
import inspect

class NodeMetadata(BaseModel):
    """Metadata for a node type to be rendered in the UI."""
    model_config = {"arbitrary_types_allowed": True}

    id: str = Field(..., description="Unique node type identifier (matches NodeDefinition.type)")
    label: str
    category: str = "Common"
    icon: str = "🧩"
    description: str = ""
    
    # I/O Contracts
    inputs: List[str] = Field(default_factory=list, description="List of expected input parameter names")
    outputs: List[str] = Field(default_factory=list, description="List of state fields this node updates")
    
    # Configuration Schema (for UI form generation)
    # Format: { "param_name": { "type": "select", "options": [...], ... } }
    config_schema: Dict[str, Any] = Field(default_factory=dict)
    
    # Runtime binding
    node_class: Optional[Type] = Field(None, exclude=True)

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
            node_desc = description or (target_cls.__doc__ or "").strip()
            
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
        self._nodes[meta.id] = meta

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
    description="Execute children sequentially until one fails.",
    config_schema={"memory": {"type": "boolean", "default": False}}
))

node_registry.register_metadata(NodeMetadata(
    id="Selector", label="Selector", category="Control Flow", icon="❓",
    description="Execute children until one succeeds.",
    config_schema={"memory": {"type": "boolean", "default": False}}
))

node_registry.register_metadata(NodeMetadata(
    id="Parallel", label="Parallel", category="Control Flow", icon="🔀",
    description="Run children in parallel.",
    config_schema={
        "policy": {
            "type": "select", 
            "options": ["SuccessOnAll", "SuccessOnOne", "FailureOnAll", "FailureOnOne"],
            "default": "SuccessOnAll"
        }
    }
))

# 2. Debug & Action Nodes
from btflow.nodes.common.debug import Log
from btflow.nodes.common.action import Wait

node_registry.register(
    Log,
    id="Log",
    label="Log Message",
    category="Debug",
    icon="📝",
    description="Print a message to the console",
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
    description="Wait for a specified duration",
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
from btflow.patterns.react import ReActGeminiNode, ToolExecutor, IsFinalAnswer
from btflow.patterns.reflexion import SelfRefineGeminiNode, IsGoodEnough
from btflow.patterns.tools import CalculatorTool, SearchTool, WikipediaTool, ToolNode

# Tools
node_registry.register_metadata(NodeMetadata(
    id="CalculatorTool", label="Calculator", category="Tools", icon="🧮",
    description="Perform mathematical calculations",
    node_class=lambda **kwargs: ToolNode(name=kwargs.get("name", "Calculator"), tool=CalculatorTool())
))

node_registry.register_metadata(NodeMetadata(
    id="SearchTool", label="Google Search", category="Tools", icon="🔍",
    description="Search the web (requires Google Search API)",
    node_class=lambda **kwargs: ToolNode(name=kwargs.get("name", "Search"), tool=SearchTool())
))

node_registry.register_metadata(NodeMetadata(
    id="WikipediaTool", label="Wikipedia", category="Tools", icon="📖",
    description="Search and browse Wikipedia",
    node_class=lambda **kwargs: ToolNode(name=kwargs.get("name", "Wikipedia"), tool=WikipediaTool())
))

# LoopUntilSuccess
node_registry.register_metadata(NodeMetadata(
    id="LoopUntilSuccess", label="Loop Until Success", category="Control Flow", icon="🔄",
    description="Loop child until it succeeds (converts FAILURE to RUNNING).",
    config_schema={
        "max_iterations": {"type": "number", "default": 10}
    },
    node_class=LoopUntilSuccess
))
node_registry._class_map["LoopUntilSuccess"] = LoopUntilSuccess

# ReAct Nodes
node_registry.register(
    ReActGeminiNode,
    id="ReActGeminiNode", label="ReAct LLM", category="Agent (ReAct)", icon="🤖",
    description="LLM Node for ReAct Pattern (Thought/Action/Answer)",
    config_schema={
        "model": {"type": "text", "default": "gemini-2.5-flash"},
        "system_prompt": {"type": "textarea", "default": ""}
    }
)

node_registry.register(
    ToolExecutor,
    id="ToolExecutor", label="Tool Executor", category="Agent (ReAct)", icon="🛠️",
    description="Executes tools based on Action from LLM",
    config_schema={} 
)

node_registry.register(
    IsFinalAnswer,
    id="IsFinalAnswer", label="Is Final Answer?", category="Agent (ReAct)", icon="✅",
    description="Check if Final Answer is present",
    config_schema={
        "max_rounds": {"type": "number", "default": 10}
    }
)

# Reflexion Nodes
node_registry.register(
    SelfRefineGeminiNode,
    id="SelfRefineGeminiNode", label="Self-Refine LLM", category="Agent (Reflexion)", icon="🪞",
    description="Generate answer and self-evaluate score",
    config_schema={
        "model": {"type": "text", "default": "gemini-2.5-flash"}
    }
)

node_registry.register(
    IsGoodEnough,
    id="IsGoodEnough", label="Is Good Enough?", category="Agent (Reflexion)", icon="⚖️",
    description="Check if score meets threshold",
    config_schema={
        "threshold": {"type": "number", "default": 8.0},
        "max_rounds": {"type": "number", "default": 5}
    }
)
