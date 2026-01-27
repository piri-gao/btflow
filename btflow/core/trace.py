import os
import time
from contextvars import ContextVar
from dataclasses import asdict, is_dataclass
from typing import Any, Callable, Dict, List, Optional

from btflow.core.logging import logger

_listeners: List[Callable[[str, Dict[str, Any]], None]] = []
_log_enabled = os.environ.get("BTFLOW_TRACE_LOG", "0") == "1"
_context: ContextVar[Dict[str, Any]] = ContextVar("btflow_trace_context", default={})
_safe_enabled = os.environ.get("BTFLOW_TRACE_SAFE", "1") == "1"


def _safe_serialize(value: Any, *, _depth: int = 0, _max_depth: int = 4, _seen: Optional[set] = None) -> Any:
    if _seen is None:
        _seen = set()
    if _depth > _max_depth:
        return str(value)

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")

    value_id = id(value)
    if value_id in _seen:
        return "<recursion>"

    if isinstance(value, dict):
        _seen.add(value_id)
        return {
            str(k): _safe_serialize(v, _depth=_depth + 1, _max_depth=_max_depth, _seen=_seen)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        _seen.add(value_id)
        return [
            _safe_serialize(v, _depth=_depth + 1, _max_depth=_max_depth, _seen=_seen)
            for v in value
        ]

    if is_dataclass(value):
        try:
            return _safe_serialize(asdict(value), _depth=_depth + 1, _max_depth=_max_depth, _seen=_seen)
        except Exception:
            return str(value)

    if hasattr(value, "model_dump"):
        try:
            return _safe_serialize(value.model_dump(), _depth=_depth + 1, _max_depth=_max_depth, _seen=_seen)
        except Exception:
            return str(value)

    if hasattr(value, "dict"):
        try:
            return _safe_serialize(value.dict(), _depth=_depth + 1, _max_depth=_max_depth, _seen=_seen)
        except Exception:
            return str(value)

    return str(value)


def subscribe(callback: Callable[[str, Dict[str, Any]], None]) -> None:
    _listeners.append(callback)


def unsubscribe(callback: Callable[[str, Dict[str, Any]], None]) -> None:
    try:
        _listeners.remove(callback)
    except ValueError:
        pass


def set_context(**kwargs: Any):
    """Set trace context for the current task."""
    current = dict(_context.get())
    current.update(kwargs)
    return _context.set(current)


def reset_context(token) -> None:
    _context.reset(token)


def emit(event: str, payload: Dict[str, Any] | None = None) -> None:
    if not _listeners and not _log_enabled:
        return

    data: Dict[str, Any] = {"event": event, "ts": time.time()}
    if payload:
        data.update(payload)
    ctx = _context.get()
    if ctx:
        data.update(ctx)

    if _safe_enabled:
        data = _safe_serialize(data)
        if not isinstance(data, dict):
            data = {"event": event, "ts": time.time(), "payload": data}

    if _log_enabled:
        logger.debug("📡 [Trace] {} {}", event, data)

    for cb in list(_listeners):
        try:
            cb(event, data)
        except Exception as exc:
            logger.warning("⚠️ [Trace] Listener failed: {}", exc)


__all__ = ["emit", "subscribe", "unsubscribe", "set_context", "reset_context"]
