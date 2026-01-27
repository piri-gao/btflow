"""
BTflow: Event-driven, State-managed Behavior Tree Framework for LLM Agents.
"""
# Core components
from btflow.core.decorators import action
from btflow.core.agent import BTAgent
from btflow.core.state import ActionField, StateManager
from btflow.core.behaviour import AsyncBehaviour
from btflow.core.runtime import ReactiveRunner
from btflow.core.persistence import SimpleCheckpointer
from btflow.core.trace import (
    emit as trace_emit,
    subscribe as trace_subscribe,
    unsubscribe as trace_unsubscribe,
    set_context as trace_set_context,
    reset_context as trace_reset_context,
)

# Re-export py_trees composites for convenience
from py_trees.composites import Sequence, Selector, Parallel, Composite
from py_trees.decorators import FailureIsSuccess, SuccessIsFailure, Inverter, Decorator
from py_trees.behaviours import Dummy
from py_trees.visitors import VisitorBase

# Re-export py_trees common types
from py_trees.common import Status, ParallelPolicy
from py_trees.behaviour import Behaviour
from py_trees.trees import BehaviourTree
from py_trees.blackboard import Client as BlackboardClient
from py_trees import display

# Re-export common nodes
from btflow.nodes.llm import GeminiNode
from btflow.nodes.common import MockLLMAction, Log, Wait

__all__ = [
    # Core
    "BTAgent",
    "StateManager",
    "ActionField",
    "AsyncBehaviour",
    "ReactiveRunner",
    "SimpleCheckpointer",
    "trace_emit",
    "trace_subscribe",
    "trace_unsubscribe",
    "trace_set_context",
    "trace_reset_context",
    # Decorators
    "action",
    # py_trees composites
    "Sequence",
    "Selector",
    "Parallel",
    "Composite",
    # py_trees decorators
    "FailureIsSuccess",
    "SuccessIsFailure",
    "Inverter",
    "Decorator",
    "Dummy",
    "VisitorBase",
    # py_trees common
    "Status",
    "ParallelPolicy",
    "Behaviour",
    "BehaviourTree",
    "BlackboardClient",
    "display",
    # Nodes
    "GeminiNode",
    "MockLLMAction",
    "Log",
    "Wait",
]
