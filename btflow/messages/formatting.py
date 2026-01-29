from typing import Any, List

from btflow.messages.base import Message


def content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, bytes):
        return content.decode("utf-8", "replace")
    if isinstance(content, dict):
        for key in ("text", "content", "data", "value"):
            value = content.get(key)
            if isinstance(value, str):
                return value
        return str(content)
    if isinstance(content, list):
        parts = [content_to_text(item) for item in content]
        return "\n".join([p for p in parts if p])
    return str(content)


def message_to_text(msg: Any) -> str:
    if isinstance(msg, Message):
        return content_to_text(msg.content)
    return content_to_text(msg)


def messages_to_prompt(messages: List[Message]) -> str:
    """Serialize Message list into a simple text prompt."""
    lines = []
    for msg in messages:
        content = message_to_text(msg)
        if msg.role == "system":
            lines.append(f"System: {content}")
        elif msg.role == "user":
            lines.append(f"User: {content}")
        elif msg.role == "assistant":
            lines.append(f"Assistant: {content}")
        elif msg.role == "tool":
            lines.append(f"Observation: {content}")
        else:
            lines.append(f"{msg.role}: {content}")
    return "\n".join(lines)


__all__ = ["messages_to_prompt", "content_to_text", "message_to_text"]
