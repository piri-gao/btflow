from typing import List, Dict, Any, Optional, Literal, Tuple
from pydantic import BaseModel, Field

# Pydantic models for Workflow JSON Schema

class Position(BaseModel):
    x: float
    y: float

class NodeDefinition(BaseModel):
    id: str = Field(..., description="Unique node instance ID")
    type: str = Field(..., description="Node type identifier (e.g., 'LLMBrain', 'Sequence')")
    position: Position = Field(default_factory=lambda: Position(x=0, y=0))
    config: Dict[str, Any] = Field(default_factory=dict, description="Node configuration parameters")
    
    # UI specific metadata (label, notes, etc.)
    label: Optional[str] = None

class EdgeDefinition(BaseModel):
    id: str = Field(..., description="Unique edge ID")
    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    type: str = Field(default="default", description="Edge type (default, parallel, etc.)")
    
    # UI handles for explicit connection points (optional)
    sourceHandle: Optional[str] = None
    targetHandle: Optional[str] = None

class StateFieldDefinition(BaseModel):
    name: str
    type: str = "str"
    default: Any = None
    is_action: bool = False
    description: Optional[str] = None

class StateDefinition(BaseModel):
    schema_name: str = "AgentState"
    fields: List[StateFieldDefinition] = Field(default_factory=list)

class WorkflowDefinition(BaseModel):
    version: str = "1.0"
    id: Optional[str] = None
    name: str = "Untitled Workflow"
    description: Optional[str] = None
    
    nodes: List[NodeDefinition] = Field(default_factory=list)
    edges: List[EdgeDefinition] = Field(default_factory=list)
    
    state: StateDefinition = Field(default_factory=StateDefinition)
    
    # Global settings
    settings: Dict[str, Any] = Field(default_factory=dict)
