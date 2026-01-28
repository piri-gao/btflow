import os
import time
import uuid
import contextvars
from dataclasses import dataclass, field, asdict, is_dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from btflow.core.logging import logger

_listeners: List[Callable[[str, Dict[str, Any]], None]] = []
_log_enabled = os.environ.get("BTFLOW_TRACE_LOG", "0") == "1"
_safe_enabled = os.environ.get("BTFLOW_TRACE_SAFE", "1") == "1"


@dataclass
class TraceContext:
    trace_id: str
    span_stack: Tuple[str, ...] = field(default_factory=tuple)
    metadata: Dict[str, Any] = field(default_factory=dict)


_context: contextvars.ContextVar[Optional[TraceContext]] = contextvars.ContextVar("btflow_trace_context", default=None)


@dataclass
class Span:
    id: str
    trace_id: str
    parent_id: Optional[str]
    name: str
    start_time: float
    end_time: Optional[float] = None
    status: str = "running"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return (time.time() - self.start_time) * 1000
        return (self.end_time - self.start_time) * 1000


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


def current_context() -> Optional[TraceContext]:
    return _context.get()


def get_current_span_id() -> Optional[str]:
    ctx = _context.get()
    if ctx and ctx.span_stack:
        return ctx.span_stack[-1]
    return None

def get_trace_id() -> Optional[str]:
    ctx = _context.get()
    return ctx.trace_id if ctx else None


def set_context(trace_id: Optional[str] = None, **metadata: Any) -> contextvars.Token:
    ctx = _context.get()
    if trace_id is None:
        trace_id = ctx.trace_id if ctx else str(uuid.uuid4())
    merged_metadata: Dict[str, Any] = dict(ctx.metadata) if ctx and ctx.metadata else {}
    merged_metadata.update(metadata)
    span_stack = ctx.span_stack if ctx else ()
    return _context.set(TraceContext(trace_id=trace_id, span_stack=span_stack, metadata=merged_metadata))


def reset_context(token: Optional[contextvars.Token]) -> None:
    if token is None:
        return
    _context.reset(token)


class span:
    def __init__(self, name: str, **kwargs):
        self.name = name
        self.metadata = kwargs
        self.span_obj: Optional[Span] = None
        self.token: Optional[contextvars.Token] = None

    def __enter__(self):
        ctx = _context.get()
        trace_id = ctx.trace_id if ctx else str(uuid.uuid4())
        parent_id = ctx.span_stack[-1] if ctx and ctx.span_stack else None
        span_id = str(uuid.uuid4())
        new_stack = (ctx.span_stack if ctx else ()) + (span_id,)
        new_metadata = dict(ctx.metadata) if ctx and ctx.metadata else {}
        self.token = _context.set(TraceContext(trace_id=trace_id, span_stack=new_stack, metadata=new_metadata))

        self.span_obj = Span(
            id=span_id,
            trace_id=trace_id,
            parent_id=parent_id,
            name=self.name,
            start_time=time.time(),
            metadata=self.metadata
        )

        emit("span_start", {
            "span_id": span_id,
            "parent_id": parent_id,
            "trace_id": trace_id,
            "name": self.name,
            **self.metadata
        })
        return self.span_obj

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.span_obj:
            self.span_obj.end_time = time.time()
            self.span_obj.status = "error" if exc_type else "success"

            payload = {
                "span_id": self.span_obj.id,
                "trace_id": self.span_obj.trace_id,
                "name": self.span_obj.name,
                "status": self.span_obj.status,
                "duration_ms": self.span_obj.duration_ms,
            }
            if exc_val:
                payload["error"] = str(exc_val)

            emit("span_end", payload)

        if self.token is not None:
            _context.reset(self.token)


def emit(event: str, payload: Dict[str, Any] | None = None) -> None:
    if not _listeners and not _log_enabled:
        return

    data: Dict[str, Any] = {"event": event, "ts": time.time()}
    if payload:
        data.update(payload)

    ctx = _context.get()
    if "trace_id" not in data:
        tid = ctx.trace_id if ctx else None
        if tid:
            data["trace_id"] = tid

    if "span_id" not in data:
        sid = ctx.span_stack[-1] if ctx and ctx.span_stack else None
        if sid:
            data["span_id"] = sid

    if ctx and ctx.metadata:
        for key, value in ctx.metadata.items():
            data.setdefault(key, value)

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


__all__ = [
    "emit",
    "subscribe",
    "unsubscribe",
    "span",
    "current_context",
    "get_trace_id",
    "get_current_span_id",
    "set_context",
    "reset_context",
]
