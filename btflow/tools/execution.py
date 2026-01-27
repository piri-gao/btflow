import asyncio
import inspect
import os
from collections.abc import Mapping as AbcMapping
from typing import Any, Dict, Optional, Tuple, Union, get_args, get_origin, get_type_hints
from types import UnionType

from btflow.core.logging import logger
from btflow.tools.base import Tool

_allow_untyped_injection = os.environ.get("BTFLOW_ALLOW_UNTYPED_INJECTION", "0") == "1"

def get_call_mode(func) -> str:
    """
    Determine if a function should be called with a single argument or kwargs.
    Returns "single" or "kwargs".
    """
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return "single"
    params = list(sig.parameters.values())
    if any(p.kind == p.VAR_KEYWORD for p in params):
        return "kwargs"
    # If there's 0 or 1 parameter, we treat it as single arg mode (or optional single)
    if len(params) <= 1:
        return "single"
    return "kwargs"

def coerce_single_arg(args: Any) -> Any:
    """
    Transform dictionary arguments into a single value if possible/needed.
    Used when a tool expects a single argument but receives a dict (common from LLMs).
    """
    if not isinstance(args, dict):
        return args
    if not args:
        return None
    # If "input" is the only key, unwrap it
    if "input" in args and len(args) == 1:
        return args["input"]
    # If there's exactly one key, unwrap it
    if len(args) == 1:
        return next(iter(args.values()))
    # Otherwise return as is (could be a dict input for a single-arg function)
    return args

def _merge_args(
    args: Any,
    injected: Optional[Dict[str, Any]],
    func,
    prefer_injected: bool,
) -> Tuple[Any, Optional[str]]:
    """
    Merge injected args with LLM args and decide if we should force a call mode.
    Returns (merged_args, forced_mode) where forced_mode is "kwargs", "single", or None.
    """
    if not injected:
        return args, None

    try:
        sig = inspect.signature(func)
        params = [p for p in sig.parameters.values() if p.name != "self"]
        type_hints = get_type_hints(func)
    except Exception:
        # Fallback if signature or type hints fail (e.g. NameError on forward refs)
        params = []
        type_hints = {}
        # If we can't inspect, we can't safely inject unless it's a known kwargs tool.
        # But for robustness, if args is dict, let's try shallow merge if we can't determine otherwise?
        # Better safe: if we can't inspect, treat as black box. If args is dict, merge.
        if isinstance(args, dict):
             merged = {**args, **injected} if prefer_injected else {**injected, **args}
             return merged, None
        return args, None

    # Check for *args (VAR_POSITIONAL) without **kwargs
    has_var_args = any(p.kind == p.VAR_POSITIONAL for p in params)
    has_kwargs = any(p.kind == p.VAR_KEYWORD for p in params)
    
    if has_var_args and not has_kwargs:
        logger.warning(
            "⚠️ [Tool] Injection skipped for tool '{}': has *args but no **kwargs.",
            getattr(func, "__name__", "run")
        )
        return args, None

    # Logic for merging
    first_name = params[0].name if params else "input"
    
    # CASE 1: Args is already a dict
    if isinstance(args, dict):
        # Even if it is a dict, we must check if the tool actually SUPPORTS extra keys
        # or if it is a single-param tool expecting a specific dict structure.
        
        # If tool supports **kwargs or multi-params -> Safe to merge
        if has_kwargs or len(params) > 1:
            merged = {**args, **injected} if prefer_injected else {**injected, **args}
            return merged, None # Let execute_tool detect mode
            
        # If tool is single param (and no kwargs)
        # We must check if that single param explicitly allows permissive dict input (Any, dict, etc.)
        # If hint is strict (e.g. TypedDict or specific class), we technically shouldn't merge blindly,
        # but detecting TypedDict structure matches is hard.
        # Generally: if it's single param, check _allow_dict_injection.
        hint = type_hints.get(first_name)
        if _allow_dict_injection(hint):
             merged = {**args, **injected} if prefer_injected else {**injected, **args}
             return merged, None
             
        # Otherwise: Single param scalar/strict -> Skip Injection
        logger.warning(
            "⚠️ [Tool] Injection skipped for single-arg tool '{}' (input is dict, hint={}).",
            getattr(func, "__name__", "run"),
            hint,
        )
        return args, None

    # CASE 2: Args is primitive (scalar) -> Bind to first param
    merged = {first_name: args}
    merged = {**merged, **injected} if prefer_injected else {**injected, **merged}

    if has_kwargs or len(params) > 1:
        return merged, "kwargs"

    # Single-param tool checks
    hint = type_hints.get(first_name)
    if _allow_dict_injection(hint):
        return merged, "single"

    logger.warning(
        "⚠️ [Tool] Context injection skipped for single-arg tool '{}' (hint={}). "
        "Consider adding **kwargs or explicit params.",
        getattr(func, "__name__", "run"),
        hint,
    )
    return args, None


def _allow_dict_injection(hint: Any) -> bool:
    if hint is None:
        return _allow_untyped_injection
    if hint is Any:
        return True

    if hint in (dict, Dict, AbcMapping):
        return True

    origin = get_origin(hint)
    if origin in (dict, Dict, AbcMapping):
        return True

    if origin in (list, tuple):
        return False

    if origin in (UnionType, Union):
        return any(_allow_dict_injection(arg) for arg in get_args(hint))

    if origin is None and hasattr(hint, "__origin__"):
        origin = hint.__origin__
        if origin in (dict, Dict, AbcMapping):
            return True

    if origin is UnionType or origin is Union:
        return any(_allow_dict_injection(arg) for arg in get_args(hint))

    return False


async def execute_tool(
    tool: Tool,
    args: Any,
    injected: Optional[Dict[str, Any]] = None,
    prefer_injected: bool = True,
) -> Any:
    """
    Execute a tool with smart argument unpacking.
    """
    # [Fix] FunctionTool Proxying: Inspect the underlying function if available
    # FunctionTool stores the real function in _fn
    run_method = tool.run
    inspect_target = getattr(tool, "_fn", run_method)
    
    # Use inspect_target for all signature analysis
    call_args, forced_mode = _merge_args(args, injected, inspect_target, prefer_injected)

    if forced_mode == "kwargs":
        return await _call_kwargs(run_method, call_args)
    if forced_mode == "single":
        return await _call_single(run_method, call_args)

    if not isinstance(call_args, dict):
        return await _call_single(run_method, call_args)

    mode = get_call_mode(inspect_target)
    if mode == "single":
        payload = coerce_single_arg(call_args)
        return await _call_single(run_method, payload)

    # kwargs mode
    return await _call_kwargs(run_method, call_args)

async def _call_single(func, payload: Any) -> Any:
    if inspect.iscoroutinefunction(func):
        return await func(payload)
    result = await asyncio.to_thread(func, payload)
    if asyncio.iscoroutine(result):
        return await result
    return result


async def _call_kwargs(func, kwargs: Dict[str, Any]) -> Any:
    if inspect.iscoroutinefunction(func):
        return await func(**kwargs)
    result = await asyncio.to_thread(func, **kwargs)
    if asyncio.iscoroutine(result):
        return await result
    return result
