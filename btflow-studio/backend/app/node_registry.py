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
from btflow.nodes.debug import Log
from btflow.nodes.action import Wait

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
