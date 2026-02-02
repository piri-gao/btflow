"""
BTflow Nodes Base Module.

This module re-exports the core AsyncBehaviour class and other base classes
to provide a single entry point for creating custom nodes.
"""
from btflow.core.behaviour import AsyncBehaviour
from btflow.core.composites import LoopUntilSuccess
from py_trees.composites import Sequence, Selector, Parallel
from py_trees.behaviour import Behaviour

# Semantic Aliases
# Node: The most generic base class (synchronous)
Node = Behaviour
# AsyncNode: The async-enabled base class for long-running IO
AsyncNode = AsyncBehaviour

__all__ = [
    "Node",
    "AsyncNode",
    "Behaviour",
    "AsyncBehaviour",
    "Sequence",
    "Selector",
    "Parallel",
    "LoopUntilSuccess",
]
