"""
BTflow Patterns: Common agent patterns built on btflow.
"""
from btflow.patterns.tools import Tool, CalculatorTool, SearchTool, WikipediaTool
from btflow.patterns.react import (
    ReActState,
    ReActGeminiNode,
    ToolExecutor,
    IsFinalAnswer,
    ReActAgent
)
from btflow.patterns.reflexion import (
    ReflexionState,
    SelfRefineGeminiNode,
    IsGoodEnough,
    ReflexionAgent
)

__all__ = [
    # Tools
    "Tool",
    "CalculatorTool",
    "SearchTool", 
    "WikipediaTool",
    # ReAct Pattern
    "ReActState",
    "ReActGeminiNode",
    "ToolExecutor",
    "IsFinalAnswer",
    "ReActAgent",
    # Reflexion Pattern
    "ReflexionState",
    "SelfRefineGeminiNode",
    "IsGoodEnough",
    "ReflexionAgent",
]
