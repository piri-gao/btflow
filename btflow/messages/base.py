from typing import Any, Dict, Optional, Union, List
from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str
    # content can be text or structured blocks (e.g., multimodal/tool payloads)
    content: Union[str, List[Any]]
    name: Optional[str] = None
    tool: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "role": self.role,
            "content": self.content,
        }
        if self.name:
            data["name"] = self.name
        if self.tool:
            data["tool"] = self.tool
        if self.tool_calls:
            data["tool_calls"] = self.tool_calls
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data


# Lightweight factories for readability

def system(content: str, **kwargs) -> Message:
    return Message(role="system", content=content, **kwargs)


def human(content: str, **kwargs) -> Message:
    return Message(role="user", content=content, **kwargs)


def ai(content: str, **kwargs) -> Message:
    return Message(role="assistant", content=content, **kwargs)


def tool(content: str, name: Optional[str] = None, **kwargs) -> Message:
    return Message(role="tool", content=content, name=name, **kwargs)
