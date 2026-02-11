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
    input_bindings: Dict[str, str] = Field(default_factory=dict, description="Input port bindings to state")
    output_bindings: Dict[str, str] = Field(default_factory=dict, description="Output port bindings to state")
    
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

class MemoryResource(BaseModel):
    id: str = "default"
    type: Literal["sqlite", "json", "in_memory"] = "sqlite"
    persist_path: Optional[str] = None
    embedding_dim: int = 64
    normalize_embeddings: bool = True
    max_size: Optional[int] = None
    autosave: bool = True

class MCPToolDefinition(BaseModel):
    name: str
    description: str = ""
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)

class MCPServerResource(BaseModel):
    id: str
    transport: Literal["stdio", "http", "sse"] = "stdio"
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    url: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)
    headers: Dict[str, str] = Field(default_factory=dict)
    auth: Optional[str] = None
    allowlist: Optional[List[str]] = None
    tools: List[MCPToolDefinition] = Field(default_factory=list)

class ResourcesDefinition(BaseModel):
    memories: List[MemoryResource] = Field(default_factory=list)
    mcp_servers: List[MCPServerResource] = Field(default_factory=list)

class WorkflowDefinition(BaseModel):
    version: str = "1.0"
    id: Optional[str] = None
    name: str = "Untitled Workflow"
    description: Optional[str] = None
    
    nodes: List[NodeDefinition] = Field(default_factory=list)
    edges: List[EdgeDefinition] = Field(default_factory=list)
    
    state: StateDefinition = Field(default_factory=StateDefinition)

    resources: ResourcesDefinition = Field(default_factory=ResourcesDefinition)
    
    # Global settings
    settings: Dict[str, Any] = Field(default_factory=dict)
