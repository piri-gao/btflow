"""
BTflow Nodes: LLM provider nodes.
"""

__all__ = ["GeminiNode"]


def __getattr__(name: str):
    if name == "GeminiNode":
        from btflow.nodes.llm.gemini import GeminiNode
        return GeminiNode
    raise AttributeError(f"module 'btflow.nodes.llm' has no attribute '{name}'")


def __dir__():
    return sorted(__all__)
