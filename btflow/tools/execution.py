import asyncio
import inspect
from typing import Any, Dict, Optional

from btflow.tools.base import Tool


async def execute_tool(
    tool: Tool,
    args: Any,
    injected: Optional[Dict[str, Any]] = None,
    prefer_injected: bool = True,
) -> Any:
    """
    Execute a tool with the given arguments.
    
    Args:
        tool: The tool to execute
        args: Arguments from LLM (dict or single value)
        injected: Optional context to inject (e.g., from state)
        prefer_injected: If True, injected values override args
    
    Returns:
        Tool execution result
    """
    run_method = tool.run
    
    # Merge injected context if provided
    if injected and isinstance(args, dict):
        if prefer_injected:
            call_args = {**args, **injected}
        else:
            call_args = {**injected, **args}
    else:
        call_args = args
    
    # Determine call style based on args type
    if isinstance(call_args, dict):
        return await _call_kwargs(run_method, call_args)
    else:
        return await _call_single(run_method, call_args)


async def _call_single(func, payload: Any) -> Any:
    """Call function with single argument."""
    if inspect.iscoroutinefunction(func):
        return await func(payload)
    return await asyncio.to_thread(func, payload)


async def _call_kwargs(func, kwargs: Dict[str, Any]) -> Any:
    """Call function with keyword arguments."""
    if inspect.iscoroutinefunction(func):
        return await func(**kwargs)
    return await asyncio.to_thread(func, **kwargs)


__all__ = ["execute_tool"]
