import asyncio
import inspect
from typing import Any, Dict, Optional

from py_trees.common import Status

from btflow.core.behaviour import AsyncBehaviour
from btflow.core.logging import logger
from btflow.core.trace import emit as trace_emit
from btflow.tools.base import Tool


class ToolNode(AsyncBehaviour):
    """
    Tool wrapper to allow a Tool to be used as a node in the tree.
    Supports two modes:
      - Workflow mode: executes tool directly using input_key/output_key (bindings-friendly).
      - Agent mode: tool can still be exposed to LLM via ToolExecutor.
    """

    def __init__(
        self,
        name: str,
        tool: Tool,
        input_map: Optional[Dict[str, Any]] = None,
        output_key: Optional[str] = "output",
        *,
        input_key: str = "input",
        execute: Optional[bool] = None,
        strict_output_validation: bool = False,
    ):
        super().__init__(name)
        self.tool = tool
        self.input_key = input_key
        self.input_map = input_map or {}
        self.output_key = output_key
        # Default: execute unless explicitly disabled
        self.execute = True if execute is None else execute
        self._warned_no_input = False
        self.strict_output_validation = strict_output_validation

    async def update_async(self) -> Status:
        if not self.execute:
            if not self._warned_no_input:
                logger.warning(
                    "⚠️ [{}] ToolNode execute=False (skipping tool execution).",
                    self.name,
                )
                self._warned_no_input = True
            logger.debug("🧩 [{}] ToolNode execute=False, skip.", self.name)
            return Status.SUCCESS

        if not self.state_manager:
            logger.error("❌ [{}] state_manager 未注入", self.name)
            return Status.FAILURE

        try:
            tool_args = self._resolve_inputs(allow_non_dict=True)
            trace_emit("tool_call", {
                "node": self.name,
                "tool": getattr(self.tool, "name", type(self.tool).__name__),
                "mode": "workflow",
                "args": tool_args,
            })
            result = await self._run_tool(tool_args)
            output_error = self._validate_tool_output(result)
            if output_error:
                logger.warning(
                    "⚠️ [{}] Tool '{}' output mismatch schema: {}",
                    self.name,
                    getattr(self.tool, "name", type(self.tool).__name__),
                    output_error,
                )
                if self.strict_output_validation:
                    trace_emit("tool_result", {
                        "node": self.name,
                        "tool": getattr(self.tool, "name", type(self.tool).__name__),
                        "ok": False,
                        "error": output_error,
                    })
                    return Status.FAILURE

            payload = result

            if self.output_key:
                self.state_manager.update({self.output_key: payload})

            trace_emit("tool_result", {
                "node": self.name,
                "tool": getattr(self.tool, "name", type(self.tool).__name__),
                "ok": True,
            })
            return Status.SUCCESS
        except Exception as e:
            logger.warning("⚠️ [{}] 工具执行失败: {}", self.name, e)
            trace_emit("tool_result", {
                "node": self.name,
                "tool": getattr(self.tool, "name", type(self.tool).__name__),
                "ok": False,
                "error": str(e),
            })
            return Status.FAILURE

    def as_tool_definition(self):
        """Expose tool schema for LLM selection."""
        return self.tool.spec()

    async def invoke_from_agent(self, args: Any):
        """Invoke tool directly from agent/router."""
        injected = self._resolve_inputs(allow_non_dict=False)
        return await self._run_tool(args, injected=injected)

    def _resolve_inputs(self, allow_non_dict: bool = True) -> Any:
        if not self.state_manager:
            return {} if allow_non_dict else {}
        if not self.input_map:
            state = self.state_manager.get()
            value = getattr(state, self.input_key, None)
            if allow_non_dict:
                return {} if value is None else value
            return value if isinstance(value, dict) else {}

        state = self.state_manager.get()
        try:
            state_data = state.model_dump()
        except Exception:
            state_data = state

        resolved: Dict[str, Any] = {}
        for key, path in self.input_map.items():
            if isinstance(path, str):
                resolved[key] = self._resolve_path(state_data, path)
            else:
                resolved[key] = path
        return resolved

    def _resolve_path(self, data: Any, path: str) -> Any:
        current = data
        for part in path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                current = getattr(current, part, None)
            if current is None:
                break
        return current

    def _validate_tool_output(self, output: Any) -> Optional[str]:
        # Schema validation removed - rely on strict_tools or Pydantic
        return None

    async def _run_tool(self, args: Any, injected: Optional[Dict[str, Any]] = None) -> Any:
        from btflow.tools.base import execute_tool
        return await execute_tool(self.tool, args, injected=injected)


__all__ = ["ToolNode"]
