import inspect
import asyncio
from typing import Callable, Any, Dict, Optional
from py_trees.common import Status
from btflow.core.behaviour import AsyncBehaviour
from btflow.core.state import StateManager
from btflow.core.logging import logger

def _get_metadata(func: Callable, name: Optional[str] = None, description: Optional[str] = None):
    """Utility to extract name and description from a function."""
    final_name = name or func.__name__
    final_desc = description or (func.__doc__ or "").strip() or ""
    return final_name, final_desc

class FunctionNode(AsyncBehaviour):
    """
    Node implementation that wraps a simple function.
    """
    def __init__(self, name: str, state_manager: StateManager, func: Callable):
        super().__init__(name)
        self.state_manager = state_manager
        self._func = func

    async def update_async(self) -> Status:
        try:
            if self.state_manager is None:
                logger.error("❌ [{}] state_manager 未注入", self.name)
                return Status.FAILURE
            current_state = self.state_manager.get()
            
            if inspect.iscoroutinefunction(self._func):
                updates = await self._func(current_state)
            else:
                updates = await asyncio.to_thread(self._func, current_state)
            
            if isinstance(updates, dict):
                self.state_manager.update(updates)
                logger.debug("   ⚡ [{}] Node finished. Updates: {}", self.name, list(updates.keys()))
            elif updates is None:
                pass
            else:
                raise ValueError(f"Node func must return a dict or None, got {type(updates)}")

            return Status.SUCCESS

        except Exception as e:
            logger.error("   🔥 [{}] Node failed: {}", self.name, e)
            self.feedback_message = str(e)
            return Status.FAILURE

def node(
    _func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
):
    """
    Decorator to wrap a function into a Node (Behavior Tree node).
    Usage:
        @node
        def my_func(state): ...
        
        @node(name="custom_name")
        def my_func(state): ...
    """
    def decorator(func: Callable):
        node_name, node_desc = _get_metadata(func, name, description)
        
        # We return a class that can be instantiated with (name, state_manager)
        # to match the existing usage pattern in tests.
        class WrappedNode(FunctionNode):
            def __init__(self, inst_name: Optional[str] = None, state_manager: Optional[StateManager] = None):
                # If name is provided during instantiation, it overrides the decorator name
                super().__init__(inst_name or node_name, state_manager, func)
                self.description = node_desc

        WrappedNode.__name__ = f"Node_{func.__name__}"
        WrappedNode.__doc__ = node_desc
        return WrappedNode

    if _func is None:
        return decorator
    return decorator(_func)

__all__ = ["node", "FunctionNode"]
