"""
BTflow Nodes: Pre-built nodes for common use cases.
"""
from btflow.nodes.common import MockLLMAction, Log, Wait

__all__ = [
    "GeminiNode",
    "MockLLMAction",
    "Log",
    "Wait",
]


def __getattr__(name: str):
    if name == "GeminiNode":
        from btflow.nodes.llm import GeminiNode
        return GeminiNode
    raise AttributeError(f"module 'btflow.nodes' has no attribute '{name}'")


def __dir__():
    return sorted(__all__)
