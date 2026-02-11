import asyncio
import json
import re
from typing import Dict, List, Optional, Any, Tuple

from py_trees.common import Status

from btflow.core.behaviour import AsyncBehaviour
from btflow.core.logging import logger
from btflow.core.trace import emit as trace_emit
from btflow.core.trace import span
from btflow.tools import Tool, ToolNode
from btflow.messages import Message, tool
from btflow.messages.formatting import message_to_text


class ToolExecutor(AsyncBehaviour):
    """
    Tool execution node for ReAct.

    Parses the latest Action/Input, invokes the matching tool, and appends
    Observations back to state.messages. Always returns SUCCESS.
    """

    ACTION_PATTERN = re.compile(
        r"Action:\s*(.+?)\s*\n\s*Input:\s*(.+)",
        re.IGNORECASE | re.DOTALL
    )

    def __init__(
        self,
        name: str = "ToolExecutor",
        tools: Optional[List[Tool]] = None,
        max_retries: int = 0,
        retry_backoff: float = 0.2,
        observation_format: str = "text",
        strict_output_validation: bool = False,
    ):
        super().__init__(name)
        self.tools: Dict[str, Tool] = {}
        self._all_tools: Dict[str, Tool] = {}
        self.tool_nodes: Dict[str, Any] = {}
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.observation_format = observation_format
        self.strict_output_validation = strict_output_validation
        if tools:
            for tool in tools:
                self.register_tool(tool)

    def setup(self, **kwargs):
        """
        Setup: Register tools from children if any.
        This allows connecting ToolNodes as children in the visual editor.
        """
        super().setup(**kwargs)

        for child in self.children:
            if hasattr(child, "invoke_from_agent") and hasattr(child, "tool"):
                self.register_tool_node(child)
            elif hasattr(child, "tool"):
                self.register_tool(child.tool)

        if hasattr(self, "state_manager") and self.state_manager:
            self._update_tools_state()

    def register_tool(self, tool: Tool):
        name_lower = tool.name.lower()
        self.tools[name_lower] = tool
        self._all_tools[name_lower] = tool
        logger.debug("🔧 [{}] 注册工具: {}", self.name, tool.name)

    def register_tool_node(self, node):
        tool = getattr(node, "tool", None)
        if tool is None:
            return
        
        name_lower = tool.name.lower()
        if name_lower in self.tool_nodes:
            logger.warning("⚠️ [{}] Overwriting existing tool node for '{}'. Previous: {}, New: {}", 
                           self.name, tool.name, self.tool_nodes[name_lower].name, node.name)
            
        self.tool_nodes[name_lower] = node
        self.register_tool(tool)
        logger.debug("🔧 [{}] 注册工具节点: {} -> {}", self.name, tool.name, node.name)

    def _update_tools_state(self):
        self.tools = {t.name.lower(): t for t in self._all_tools.values()}
        desc = self.get_tools_description()
        schema = self.get_tools_schema()
        logger.info("🔧 [{}] Updating state.tools_desc with {} tools", self.name, len(self.tools))
        self.state_manager.update({"tools_desc": desc, "tools_schema": schema})

    def get_tools_description(self) -> str:
        if not self.tools:
            return "No tools available."

        descriptions = []
        for name, tool in self.tools.items():
            spec = tool.spec() if hasattr(tool, "spec") else None
            if spec:
                descriptions.append(
                    f"- {spec['name']}: {spec['description']} "
                    f"(input: {spec['input_schema']}, output: {spec['output_schema']})"
                )
            else:
                descriptions.append(f"- {name}: {tool.description}")
        return "\n".join(descriptions)

    def get_tools_schema(self) -> List[Dict[str, Any]]:
        schema = []
        for tool in self.tools.values():
            if hasattr(tool, "to_openai"):
                schema.append(tool.to_openai())
            elif hasattr(tool, "spec"):
                spec = tool.spec()
                if isinstance(spec, dict) and "parameters" in spec:
                    schema.append({
                        "name": spec.get("name", tool.name),
                        "description": spec.get("description", tool.description),
                        "parameters": spec.get("parameters", {"type": "object"}),
                        "returns": spec.get("returns", {"type": "object"}),
                    })
            else:
                schema.append({
                    "name": tool.name,
                    "description": tool.description,
                })
        return schema

    def _normalize_tool_result(self, tool_name: str, result: Any, error: Optional[str]) -> Message:
        if self.observation_format not in ("text", "json"):
            self.observation_format = "text"

        payload = {
            "tool": tool_name,
            "ok": error is None,
            "output": None,
            "error": error,
        }

        if error is None:
            payload["output"] = result

        if self.observation_format == "json":
            content = json.dumps(payload, ensure_ascii=True)
        elif error:
            content = str(error)
        elif isinstance(result, str):
            content = result
        else:
            content = json.dumps(payload, ensure_ascii=True)
            
        return tool(content=content, name=tool_name)

    def _validate_tool_output(self, tool: Tool, output: Any) -> Optional[str]:
        # Schema validation removed - rely on strict_tools or Pydantic
        return None

    def _parse_tool_input(self, tool: Tool, raw_input: Any) -> tuple[Any, Optional[str]]:
        schema = getattr(tool, "input_schema", None) or {"type": "string"}
        schema_type = schema.get("type")
        if schema_type is None and "properties" in schema:
            schema_type = "object"
        if schema_type is None:
            schema_type = "string"

        if schema_type == "string":
            if isinstance(raw_input, str):
                return raw_input, None
            if isinstance(raw_input, dict) and "input" in raw_input and len(raw_input) == 1:
                return str(raw_input["input"]), None
            if isinstance(raw_input, dict) and len(raw_input) == 1:
                return str(next(iter(raw_input.values()))), None
            return str(raw_input), None

        # [FIX] Unwrap primitive types that were wrapped by tool schema normalization
        if schema_type != "object":
            if isinstance(raw_input, dict) and "input" in raw_input and len(raw_input) == 1:
                raw_input = raw_input["input"]

        if not isinstance(raw_input, str):
            parsed = raw_input
        else:
            try:
                parsed = json.loads(raw_input)
            except json.JSONDecodeError:
                return None, f"Invalid input for tool '{tool.name}': expected JSON {schema_type}"

        type_map = {
            "number": (int, float),
            "integer": (int,),
            "boolean": (bool,),
            "object": (dict,),
            "array": (list,),
        }
        expected = type_map.get(schema_type)
        if expected and not isinstance(parsed, expected):
            return None, f"Invalid input for tool '{tool.name}': expected {schema_type}"

        return parsed, None

    def _safe_trace_payload(self, obj: Any) -> Any:
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)

    async def _run_tool(self, tool: Tool, parsed_input: Any) -> Any:
        from btflow.tools.base import execute_tool
        return await execute_tool(tool, parsed_input)

    def _extract_tool_call_from_dict(self, data: Any) -> Optional[Tuple[str, Any]]:
        if not isinstance(data, dict):
            return None

        if "tool_calls" in data and isinstance(data["tool_calls"], list) and data["tool_calls"]:
            return self._extract_tool_call_from_dict(data["tool_calls"][0])

        if "function_call" in data and isinstance(data["function_call"], dict):
            return self._extract_tool_call_from_dict(data["function_call"])

        # [NEW] Support standard OpenAI "function" field inside tool_calls
        if "function" in data and isinstance(data["function"], dict):
            return self._extract_tool_call_from_dict(data["function"])

        tool_name = data.get("tool") or data.get("name") or data.get("tool_name")
        # [FIX] Check for presence of keys, not truthiness - empty dict {} is valid arguments
        args_container = None
        for key in ("arguments", "args", "input"):
            if key in data:
                args_container = data[key]
                break
        
        # Require tool_name; args_container can be None for tools that take no arguments
        if not tool_name:
            return None

        args = args_container
        if isinstance(args, str):
            args_str = args.strip()
            if args_str.startswith("{") or args_str.startswith("["):
                try:
                    args = json.loads(args_str)
                except json.JSONDecodeError:
                    pass

        return str(tool_name).lower(), args

    def _extract_tool_call_json(self, content: str) -> Optional[Tuple[str, Any]]:
        decoder = json.JSONDecoder()
        idx = content.find("{")
        while idx != -1:
            try:
                obj, idx_end = decoder.raw_decode(content[idx:])
                # Note: raw_decode returns (obj, end_index) where end_index is relative to string start
                # but here we passed content[idx:] so it is relative to idx.
            except json.JSONDecodeError:
                idx = content.find("{", idx + 1)
                continue
            
            extracted = self._extract_tool_call_from_dict(obj)
            if extracted:
                return extracted
            
            # [FIX] If valid JSON but not a tool call, skip past it to avoid re-scanning internals
            idx = idx + idx_end
            idx = content.find("{", idx)
        return None

    def _extract_tool_call_from_marked(self, content: str) -> Optional[Tuple[str, Any]]:
        marker = "ToolCall:"
        idx = content.find(marker)
        if idx == -1:
            return None
        # Only parse JSON after the marker to avoid false positives in Thought.
        return self._extract_tool_call_json(content[idx + len(marker):])

    def _parse_latest_action(self, messages: List[Message]) -> Optional[Tuple[str, Any]]:
        """从最近的 assistant 消息中解析单个 ToolCall / Action (backwards compatible)"""
        actions = self._parse_all_actions(messages)
        return actions[0] if actions else None

    def _parse_all_actions(self, messages: List[Message]) -> List[Tuple[str, Any]]:
        """从最近的 assistant 消息中解析所有 ToolCall / Action（支持并行调用）"""
        actions = []
        content = None
        last_msg = None
        
        for msg in reversed(messages):
            if isinstance(msg, Message) and msg.role == "assistant":
                content = message_to_text(msg)
                last_msg = msg
                break
            if not isinstance(msg, Message):
                content = message_to_text(msg)
                last_msg = msg
                break

        if content is None:
            logger.debug("📭 [{}] 未检测到可解析的 assistant 消息", self.name)
            return []

        # Priority 1: Check message.tool_calls attribute (structured calls from LLM)
        if last_msg and hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            for tc in last_msg.tool_calls:
                extracted = self._extract_tool_call_from_dict(tc)
                if extracted:
                    actions.append(extracted)
            if actions:
                return actions

        # Priority 2: ToolCall: marker in text
        extracted = self._extract_tool_call_from_marked(content)
        if extracted:
            return [extracted]

        # Priority 3: Legacy Action/Input pattern
        match = self.ACTION_PATTERN.search(content)
        if match:
            tool_name = match.group(1).strip().lower()
            tool_input = match.group(2).strip()
            return [(tool_name, tool_input)]

        logger.debug("📭 [{}] 未检测到 Action，跳过", self.name)
        return []

    def _normalize_actions(self, raw_actions: Any) -> Optional[List[Tuple[str, Any]]]:
        if raw_actions is None:
            return None
        if not isinstance(raw_actions, list):
            return []
        normalized: List[Tuple[str, Any]] = []
        for item in raw_actions:
            if isinstance(item, tuple) and len(item) == 2:
                normalized.append((str(item[0]).lower(), item[1]))
                continue
            if isinstance(item, dict):
                extracted = self._extract_tool_call_from_dict(item)
                if extracted:
                    normalized.append(extracted)
                continue
        return normalized

    async def _execute_action(self, tool_name: str, tool_input: Any) -> Message:
        """执行具体的 Action 逻辑（包含重试、Trace、Result Normalize）"""
        logger.info("⚙️ [{}] 执行 Action: {} Input: {}", self.name, tool_name, tool_input)
        
        with span("tool_execution", tool=tool_name, mode="react"):
            trace_emit("tool_call", {"node": self.name, "tool": tool_name, "mode": "react"})

            tool = self.tools.get(tool_name)
            tool_node = self.tool_nodes.get(tool_name)

            if not tool:
                logger.warning("⚠️ [{}] 未知工具: {}", self.name, tool_name)
                error_msg = f"tool_not_found: Tool '{tool_name}' not found. Available tools: {list(self.tools.keys())}"
                trace_emit("tool_result", {
                    "node": self.name,
                    "tool": tool_name,
                    "ok": False,
                    "error": "tool_not_found",
                })
                return self._normalize_tool_result(tool_name, None, error=error_msg)

            # Parse Input
            parsed_input, input_error = self._parse_tool_input(tool, tool_input)
            if input_error:
                trace_emit("tool_result", {
                    "node": self.name,
                    "tool": tool_name,
                    "ok": False,
                    "error": input_error,
                })
                return self._normalize_tool_result(tool_name, None, error=input_error)

            # Execution Loop with Retry
            attempts = 0
            while True:
                attempts += 1
                try:
                    # Execution
                    if tool_node is not None:
                        result = tool_node.invoke_from_agent(parsed_input)
                        if asyncio.iscoroutine(result):
                            result = await result

                        # ToolNode Writeback
                        if tool_node.output_key and self.state_manager:
                            self.state_manager.update({tool_node.output_key: result})
                            logger.debug("💾 [{}] ToolNode '{}' output written to key '{}'",
                                         self.name, tool_name, tool_node.output_key)
                    else:
                        result = await self._run_tool(tool, parsed_input)

                    output_error = self._validate_tool_output(tool, result)
                    if output_error:
                        logger.warning(
                            "⚠️ [{}] Tool '{}' output mismatch schema: {}",
                            self.name,
                            tool_name,
                            output_error,
                        )
                        if self.strict_output_validation:
                            observation = self._normalize_tool_result(tool_name, result, error=output_error)
                            trace_emit("tool_result", {
                                "node": self.name,
                                "tool": tool_name,
                                "ok": False,
                                "error": output_error,
                                "result": self._safe_trace_payload(result),
                            })
                            return observation

                    observation = self._normalize_tool_result(tool_name, result, error=None)
                    trace_emit("tool_result", {
                        "node": self.name,
                        "tool": tool_name,
                        "ok": True,
                        "error": None,
                        "result": self._safe_trace_payload(result),
                    })
                    return observation

                except Exception as e:
                    logger.warning("⚠️ [{}] 工具执行失败: {}", self.name, e)
                    observation = self._normalize_tool_result(tool_name, None, error=f"tool_error: {e}")
                    trace_emit("tool_result", {
                        "node": self.name,
                        "tool": tool_name,
                        "ok": False,
                        "error": str(e),
                    })
                    if attempts <= self.max_retries:
                        logger.warning(
                            "⚠️ [{}] Tool '{}' failed (attempt {}/{}), retrying... Error: {}",
                            self.name, tool_name, attempts, self.max_retries, e,
                        )
                        await asyncio.sleep(self.retry_backoff * attempts)
                        continue
                    return observation

    async def update_async(self) -> Status:
        state = self.state_manager.get()

        # 0. Use pre-parsed actions if provided (e.g., ParserNode)
        # 0. Use pre-parsed actions if provided (e.g., ParserNode or AgentLLMNode)
        actions = self._normalize_actions(getattr(state, "actions", None))
        
        # If pre-parsed actions exist, use them and clear state
        if actions:
            self.state_manager.update({"actions": []})
        else:
            # Fallback: Parse all Actions from messages (legacy/standalone mode)
            if not getattr(state, "messages", []):
                return Status.SUCCESS
            actions = self._parse_all_actions(state.messages)

        if not actions:
            return Status.SUCCESS
        
        # 2. Execute Actions in parallel
        if len(actions) == 1:
            # Single action - simple path
            tool_name, tool_input = actions[0]
            observation = await self._execute_action(tool_name, tool_input)
            observations = [observation]
        else:
            # Multiple actions - parallel execution
            logger.info("🔀 [{}] Executing {} tools in parallel", self.name, len(actions))
            coroutines = [self._execute_action(name, inp) for name, inp in actions]
            observations = await asyncio.gather(*coroutines, return_exceptions=True)
            
            # Handle exceptions gracefully
            processed = []
            for i, obs in enumerate(observations):
                if isinstance(obs, Exception):
                    tool_name = actions[i][0]
                    logger.error("❌ [{}] Tool '{}' raised exception: {}", self.name, tool_name, obs)
                    processed.append(self._normalize_tool_result(tool_name, None, error=str(obs)))
                else:
                    processed.append(obs)
            observations = processed

        # 3. Update State with all observations
        self.state_manager.update({"messages": observations})
        return Status.SUCCESS


__all__ = ["ToolExecutor", "ToolNode"]
