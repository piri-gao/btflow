from typing import List

from btflow.messages import Message


def messages_to_prompt(messages: List[Message]) -> str:
    """Serialize Message list into a simple text prompt."""
    lines = []
    for msg in messages:
        if msg.role == "system":
            lines.append(f"System: {msg.content}")
        elif msg.role == "user":
            lines.append(f"User: {msg.content}")
        elif msg.role == "assistant":
            lines.append(f"Assistant: {msg.content}")
        elif msg.role == "tool":
            lines.append(f"Observation: {msg.content}")
        else:
            lines.append(f"{msg.role}: {msg.content}")
    return "\n".join(lines)
