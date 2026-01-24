from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Message:
    role: str
    content: str
    name: Optional[str] = None
    tool: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "role": self.role,
            "content": self.content,
        }
        if self.name:
            data["name"] = self.name
        if self.tool:
            data["tool"] = self.tool
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
