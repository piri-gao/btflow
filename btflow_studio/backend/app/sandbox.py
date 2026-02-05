from __future__ import annotations

import asyncio
import inspect
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional, Set, Tuple, Type

from btflow.core.logging import logger

try:
    import yaml
except Exception:  # pragma: no cover - optional dependency
    yaml = None


_CONFIG_ENV = "BTFLOW_SANDBOX_CONFIG"

_DEFAULT_CONFIG = {
    "enabled": True,
    "tools": {
        "allow": [],
        "deny": ["FileReadTool", "FileWriteTool"],
    },
    "file_access": {
        "enabled": True,
        "read_paths": ["."],
        "write_paths": ["."],
    },
    "network": {
        "enabled": False,
    },
}

_FILE_TOOL_NAMES = {"filereadtool", "filewritetool", "read_file", "write_file"}
_NETWORK_TOOL_NAMES = {"httptool", "duckduckgosearchtool", "http_request", "duckduckgo_search"}


def _normalize_names(values: Iterable[str]) -> Set[str]:
    return {str(v).strip().lower() for v in values if str(v).strip()}


def _resolve_paths(paths: Iterable[str], base_dir: Path) -> Tuple[Path, ...]:
    resolved = []
    for raw in paths:
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        path = Path(os.path.expanduser(text))
        if not path.is_absolute():
            path = (base_dir / path).resolve()
        else:
            path = path.resolve()
        resolved.append(path)
    return tuple(resolved)


def _tool_name_candidates(tool_or_cls: Any) -> Set[str]:
    names = set()
    if tool_or_cls is None:
        return names
    if isinstance(tool_or_cls, type):
        names.add(tool_or_cls.__name__)
        name_attr = getattr(tool_or_cls, "name", None)
        if name_attr:
            names.add(str(name_attr))
    else:
        names.add(tool_or_cls.__class__.__name__)
        name_attr = getattr(tool_or_cls, "name", None)
        if name_attr:
            names.add(str(name_attr))
    return _normalize_names(names)


def _is_file_tool(tool_or_cls: Any) -> bool:
    return bool(_tool_name_candidates(tool_or_cls) & _FILE_TOOL_NAMES)


def _is_network_tool(tool_or_cls: Any) -> bool:
    return bool(_tool_name_candidates(tool_or_cls) & _NETWORK_TOOL_NAMES)


def _extract_path(args: tuple, kwargs: dict) -> Optional[str]:
    if "path" in kwargs and kwargs["path"] is not None:
        return str(kwargs["path"])
    if "input" in kwargs and isinstance(kwargs["input"], str):
        return kwargs["input"]
    if args:
        first = args[0]
        if isinstance(first, dict):
            if "path" in first and first["path"] is not None:
                return str(first["path"])
            if "input" in first and isinstance(first["input"], str):
                return first["input"]
        if isinstance(first, str):
            return first
    return None


@dataclass
class SandboxPolicy:
    enabled: bool = True
    tool_allow: Set[str] = field(default_factory=set)
    tool_deny: Set[str] = field(default_factory=set)
    file_enabled: bool = True
    read_paths: Tuple[Path, ...] = field(default_factory=tuple)
    write_paths: Tuple[Path, ...] = field(default_factory=tuple)
    network_enabled: bool = False
    config_path: Optional[Path] = None

    def is_tool_allowed(self, tool_or_cls: Any) -> bool:
        if not self.enabled:
            return True
        if getattr(tool_or_cls, "sandbox_blocked", False):
            return False
        if _is_network_tool(tool_or_cls) and not self.network_enabled:
            return False
        names = _tool_name_candidates(tool_or_cls)
        if self.tool_allow:
            return bool(names & self.tool_allow)
        if names & self.tool_deny:
            return False
        return True

    def tool_disabled_reason(self, tool_or_cls: Any) -> Optional[str]:
        if not self.enabled:
            return None
        if getattr(tool_or_cls, "sandbox_blocked", False):
            return "blocked by sandbox"
        if _is_network_tool(tool_or_cls) and not self.network_enabled:
            return "network disabled by sandbox"
        names = _tool_name_candidates(tool_or_cls)
        if self.tool_allow and not (names & self.tool_allow):
            return "tool not in sandbox allowlist"
        if names & self.tool_deny:
            return "tool denied by sandbox"
        return None

    def ensure_tool_allowed(self, tool_or_cls: Any) -> None:
        reason = self.tool_disabled_reason(tool_or_cls)
        if reason:
            raise PermissionError(f"Sandbox blocked tool: {reason}")

    def _path_allowed(self, path: str, mode: str) -> bool:
        if not self.file_enabled:
            return False
        roots = self.read_paths if mode == "read" else self.write_paths
        if not roots:
            return False
        try:
            resolved = Path(path).expanduser().resolve()
        except Exception:
            return False
        for root in roots:
            try:
                resolved.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    def ensure_call_allowed(self, tool_or_cls: Any, args: tuple, kwargs: dict) -> None:
        if not self.enabled:
            return
        if _is_file_tool(tool_or_cls):
            mode = "read" if "read" in _tool_name_candidates(tool_or_cls) else "write"
            path = _extract_path(args, kwargs)
            if not path:
                raise PermissionError("Sandbox blocked file tool: missing path")
            if not self._path_allowed(path, mode):
                raise PermissionError(f"Sandbox blocked file {mode}: path not allowed")

    def wrap_tool(self, tool: Any) -> Any:
        if not self.enabled:
            return tool
        if isinstance(tool, BlockedTool):
            return tool
        return SandboxedTool(tool, self)


class BlockedTool:
    sandbox_blocked = True

    def __init__(self, name: str, reason: str):
        self.name = name
        self.description = f"Blocked by sandbox: {reason}"
        self.input_schema = {"type": "object", "properties": {}}
        self.output_schema = {"type": "string"}
        self._reason = reason

    async def run(self, *args, **kwargs):
        raise PermissionError(f"Sandbox blocked tool '{self.name}': {self._reason}")

    def spec(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "parameters": {"type": "object", "properties": {}},
            "returns": {"type": "object", "properties": {}},
        }


class SandboxedTool:
    def __init__(self, tool: Any, policy: SandboxPolicy):
        self._tool = tool
        self._policy = policy
        self.name = getattr(tool, "name", tool.__class__.__name__)
        self.description = getattr(tool, "description", "")
        self.input_schema = getattr(tool, "input_schema", {"type": "string"})
        self.output_schema = getattr(tool, "output_schema", {"type": "string"})

    async def run(self, *args, **kwargs):
        self._policy.ensure_tool_allowed(self._tool)
        self._policy.ensure_call_allowed(self._tool, args, kwargs)
        run_method = getattr(self._tool, "run")
        if inspect.iscoroutinefunction(run_method):
            return await run_method(*args, **kwargs)
        return await asyncio.to_thread(run_method, *args, **kwargs)

    def spec(self) -> dict:
        if hasattr(self._tool, "spec"):
            return self._tool.spec()
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }

    def to_openai(self) -> dict:
        if hasattr(self._tool, "to_openai"):
            return self._tool.to_openai()
        return self.spec()


def _load_config_dict(config_path: Path) -> dict:
    if not config_path.exists():
        logger.info("[sandbox] config not found at {}, using defaults", config_path)
        return dict(_DEFAULT_CONFIG)
    if yaml is None:
        logger.warning("[sandbox] PyYAML not installed; cannot read {}, using defaults", config_path)
        return dict(_DEFAULT_CONFIG)
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            logger.warning("[sandbox] config invalid, using defaults")
            return dict(_DEFAULT_CONFIG)
        merged = dict(_DEFAULT_CONFIG)
        merged.update(data)
        return merged
    except Exception as e:
        logger.warning("[sandbox] failed to read config: {}, using defaults", e)
        return dict(_DEFAULT_CONFIG)


def load_sandbox_policy() -> SandboxPolicy:
    config_path = Path(os.getenv(_CONFIG_ENV, "sandbox.yaml"))
    base_dir = Path.cwd()
    data = _load_config_dict(config_path)

    tools_cfg = data.get("tools", {}) or {}
    file_cfg = data.get("file_access", {}) or {}
    network_cfg = data.get("network", {}) or {}

    policy = SandboxPolicy(
        enabled=bool(data.get("enabled", True)),
        tool_allow=_normalize_names(tools_cfg.get("allow", []) or []),
        tool_deny=_normalize_names(tools_cfg.get("deny", []) or []),
        file_enabled=bool(file_cfg.get("enabled", True)),
        read_paths=_resolve_paths(file_cfg.get("read_paths", []) or [], base_dir),
        write_paths=_resolve_paths(file_cfg.get("write_paths", []) or [], base_dir),
        network_enabled=bool(network_cfg.get("enabled", False)),
        config_path=config_path,
    )

    logger.info(
        "[sandbox] loaded (enabled={}, network_enabled={}, file_enabled={}, allow={}, deny={})",
        policy.enabled,
        policy.network_enabled,
        policy.file_enabled,
        sorted(policy.tool_allow),
        sorted(policy.tool_deny),
    )
    return policy


_SANDBOX_POLICY: Optional[SandboxPolicy] = None


def get_sandbox_policy() -> SandboxPolicy:
    global _SANDBOX_POLICY
    if _SANDBOX_POLICY is None:
        _SANDBOX_POLICY = load_sandbox_policy()
    return _SANDBOX_POLICY


def create_tool_instance(tool_cls: Type, allow_blocked: bool = False) -> Optional[Any]:
    policy = get_sandbox_policy()
    if not policy.is_tool_allowed(tool_cls):
        reason = policy.tool_disabled_reason(tool_cls) or "blocked by sandbox"
        if allow_blocked:
            return BlockedTool(getattr(tool_cls, "name", tool_cls.__name__), reason)
        return None
    try:
        tool = tool_cls()
    except Exception as e:
        logger.warning("[sandbox] failed to instantiate tool {}: {}", tool_cls.__name__, e)
        if allow_blocked:
            return BlockedTool(getattr(tool_cls, "name", tool_cls.__name__), f"init error: {e}")
        return None
    return policy.wrap_tool(tool)
