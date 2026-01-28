import asyncio
import json
import re
from typing import Dict, List, Optional, Any, Tuple

from py_trees.common import Status
from py_trees.behaviour import Behaviour

from btflow.core.behaviour import AsyncBehaviour
from btflow.core.logging import logger
from btflow.core.logging import logger
from btflow.core.trace import emit as trace_emit
from btflow.core.trace import span
from btflow.tools import Tool

from btflow.tools.ext.policy import ToolSelectionPolicy, AllowAllToolPolicy
from btflow.tools.registry import ToolRegistry
from btflow.tools.base import ToolError, ToolResult
from btflow.tools.ext.schema import validate_json_schema
from btflow.llm import LLMProvider, GeminiProvider


from btflow.messages import Message, human, ai, tool, messages_to_prompt
from btflow.memory import BaseMemory
from btflow.context.builder import ContextBuilder, ContextBuilderProtocol

class ReActLLMNode(AsyncBehaviour):
    """
    ReAct 推理节点：调用 Gemini 进行思考。

    每次 tick 都会调用 LLM，由 Repeat 控制循环。
    """

    def __init__(
        self,
        name: str = "ReActLLM",
        model: str = "gemini-2.5-flash",
        provider: Optional[LLMProvider] = None,
        system_prompt: Optional[str] = None,
        tools_description: str = "",
        memory: Optional[BaseMemory] = None,
        memory_top_k: int = 5,
        structured_tool_calls: bool = True,
        strict_tool_calls: bool = False,
        context_builder: Optional[ContextBuilderProtocol] = None,
    ):
        super().__init__(name)
        self.model = model
        self.tools_description = tools_description
        self._uses_default_prompt = system_prompt is None
        self.system_prompt = system_prompt or self._get_default_prompt()
        self.provider = provider or GeminiProvider()
        self.structured_tool_calls = structured_tool_calls
        self.strict_tool_calls = strict_tool_calls
        
        # Internal context builder (tools are embedded in system prompt)
        if context_builder is None:
            self.context_builder = ContextBuilder(
                system_prompt=self.system_prompt,
                memory=memory,
                memory_top_k=memory_top_k,
            )
        else:
            self.context_builder = context_builder

    def _get_default_prompt(self, dynamic_tools_desc: str = "") -> str:
        description = dynamic_tools_desc or self.tools_description
        tools_section = f"\nAvailable tools:\n{description}" if description else "No tools available."

        return f"""You are a helpful assistant that can use tools to answer questions.

You must follow one of these formats:

Thought: [your reasoning about what to do next]
ToolCall: {"tool": "<tool_name>", "arguments": {...}}

OR (legacy):
Thought: [your reasoning about what to do next]
Action: [tool name]
Input: [tool input]

OR when you have the final answer:

Thought: [your final reasoning]
Final Answer: [your answer to the user]
{tools_section}

IMPORTANT RULES:
1. Always start with "Thought:" to explain your reasoning
2. Use EXACT tool names as shown above (lowercase)
3. ToolCall must be valid JSON
4. After seeing an Observation, continue with another "Thought:"
5. Only use "Final Answer:" when you have the complete answer

Always think step by step."""

    async def update_async(self) -> Status:
        """调用 Gemini 进行 ReAct 推理"""
        try:
            state = self.state_manager.get()
            messages: List[Message] = list(state.messages) if hasattr(state, "messages") else []
            task = getattr(state, "task", None)

            # Re-configure builder if tools description changed dynamically
            tools_desc = getattr(state, "tools_desc", "")
            if tools_desc and tools_desc != self.tools_description:
                 self.tools_description = tools_desc
                 # Also update system prompt if it was default
                 if self._uses_default_prompt:
                      new_prompt = self._get_default_prompt(tools_desc)
                      if hasattr(self.context_builder, "system_prompt"):
                          self.context_builder.system_prompt = new_prompt
                      elif hasattr(self.context_builder, "set_system_prompt"):
                          self.context_builder.set_system_prompt(new_prompt)

            logger.debug("📋 [{}] State dump: messages_count={}, task={}", self.name, len(messages), task)

            if not messages and task:
                logger.info("🎯 [{}] Initializing conversation with task: {}", self.name, task)
                # Initialize with HumanMessage
                initial_msg = human(f"User Question: {task}")
                messages = [initial_msg]
                self.state_manager.update({"messages": messages})
                state = self.state_manager.get()

            if not messages:
                logger.warning("⚠️ [{}] No messages and no task, cannot call LLM", self.name)
                return Status.FAILURE

            # Build full context (System + Tools + History)
            full_messages = self.context_builder.build(
                state,
                tools_schema=getattr(state, "tools_schema", None),
            )
            
            # Serialize to prompt string
            # Note: Since ReAct prompt template is complex and partly in system prompt,
            # ContextBuilder puts system prompt at the beginning.
            # We just join them for now.
            # TODO: Update LLMProvider to support List[Message] natively.
            prompt_content = messages_to_prompt(full_messages)

            logger.debug("🤖 [{}] 调用 LLM ({})...", self.name, self.model)

            # Only verify system instruction logic for providers that separate it
            # But here we embedded it in prompt_content for safety via ContextBuilder
            # For providers taking system_instruction sep, maybe redundant but safe.
            tools_schema = getattr(state, "tools_schema", None)

            with span("llm_call", model=self.model):
                trace_emit("llm_call", {
                    "node": self.name,
                    "model": self.model,
                    "messages": len(full_messages),
                })
                # logger.debug("Prompt:\n{}", prompt_content)

                response = await self.provider.generate_text(
                    prompt_content,
                    model=self.model,
                    # context_builder already added system prompt to messages
                    # system_instruction=None,
                    temperature=0.7,
                    timeout=60.0,
                    tools=tools_schema if self.structured_tool_calls else None,
                    strict_tools=self.strict_tool_calls,
                )

                content = response.text.strip()
                if response.tool_calls:
                    tool_call = response.tool_calls[0]

                    tool_name = tool_call.get("name") or tool_call.get("tool")
                    args = tool_call.get("arguments")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            pass
                    payload = {"tool": tool_name, "arguments": args}
                    thought = content
                    if thought:
                        if not thought.lower().startswith("thought:"):
                            thought = f"Thought: {thought}"
                    else:
                        thought = "Thought: calling tool"
                    content = f"{thought}\nToolCall: {json.dumps(payload, ensure_ascii=True)}"

                trace_emit("llm_response", {
                    "node": self.name,
                    "model": self.model,
                    "content_len": len(content),
                })

            if not content:
                logger.warning("⚠️ [{}] LLM 返回空响应", self.name)
                return Status.FAILURE

            # Append structured AIMessage
            new_msg = ai(content)
            self.state_manager.update({
                "messages": [new_msg],
                "round": state.round + 1
            })

            logger.info("💭 [{}] Round {} 响应:\n{}", self.name, state.round + 1, content[:200])
            return Status.SUCCESS

        except asyncio.TimeoutError:
            logger.warning("⏰ [{}] 请求超时", self.name)
            trace_emit("llm_error", {"node": self.name, "model": self.model, "error": "timeout"})
            return Status.FAILURE
        except Exception as e:
            logger.error("🔥 [{}] Gemini 调用失败: {}", self.name, e)
            trace_emit("llm_error", {"node": self.name, "model": self.model, "error": str(e)})
            return Status.FAILURE


class ToolExecutor(AsyncBehaviour):
    """
    工具执行节点：检测并执行 Action。

    解析最后一条消息中的 Action/Input，执行对应工具，
    将结果作为 Observation 写入消息历史。

    无论是否有 Action，都返回 SUCCESS（不阻塞 Sequence）。
    """

    ACTION_PATTERN = re.compile(
        r"Action:\s*(.+?)\s*\n\s*Input:\s*(.+)",
        re.IGNORECASE | re.DOTALL
    )

    def __init__(
        self,
        name: str = "ToolExecutor",
        tools: Optional[List[Tool]] = None,
        registry: Optional[ToolRegistry] = None,
        max_retries: int = 0,
        retry_backoff: float = 0.2,
        observation_format: str = "text",
        strict_output_validation: bool = False,
        policy: Optional[ToolSelectionPolicy] = None,
    ):
        super().__init__(name)
        self.tools: Dict[str, Tool] = {}
        self._all_tools: Dict[str, Tool] = {}
        self.tool_nodes: Dict[str, Any] = {}
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.observation_format = observation_format
        self.strict_output_validation = strict_output_validation
        self.policy = policy or AllowAllToolPolicy()
        if tools:
            for tool in tools:
                self.register_tool(tool)
        if registry:
            for tool in registry.list():
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
        filtered = self.policy.select_tools(self.state_manager.get(), list(self._all_tools.values()))
        self.tools = {t.name.lower(): t for t in filtered}
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
                    f"- {spec.name}: {spec.description} "
                    f"(input: {spec.input_schema}, output: {spec.output_schema})"
                )
            else:
                descriptions.append(f"- {name}: {tool.description}")
        return "\n".join(descriptions)

    def get_tools_schema(self) -> List[Dict[str, Any]]:
        schema = []
        for tool in self.tools.values():
            if hasattr(tool, "spec"):
                schema.append(tool.spec().to_openai())
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
            if hasattr(result, "to_dict"):
                try:
                    payload.update(result.to_dict())
                except Exception:
                    payload["output"] = str(result)
            else:
                payload["output"] = result

        if self.observation_format == "json":
            content = json.dumps(payload, ensure_ascii=True)
        elif error:
            content = str(error)
        elif isinstance(result, ToolResult):
            if result.ok and isinstance(result.output, str):
                content = result.output
            else:
                content = json.dumps(payload, ensure_ascii=True)
        elif isinstance(result, str):
            content = result
        else:
            content = json.dumps(payload, ensure_ascii=True)
            
        return tool(content=content, name=tool_name)

    def _coerce_tool_result(self, result: Any) -> ToolResult:
        if isinstance(result, ToolResult):
            return result
        return ToolResult(ok=True, output=result)

    def _validate_tool_output(self, tool: Tool, output: Any) -> Optional[str]:
        schema = getattr(tool, "output_schema", None) or {}
        if not schema:
            return None
        errors = validate_json_schema(output, schema)
        if errors:
            return "Invalid output for tool '{}': {}".format(tool.name, "; ".join(errors))
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

        errors = validate_json_schema(parsed, schema)
        if errors:
            return None, f"Invalid input for tool '{tool.name}': " + "; ".join(errors)

        return parsed, None

    def _safe_trace_payload(self, obj: Any) -> Any:
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)

    async def _run_tool(self, tool: Tool, parsed_input: Any) -> Any:
        from btflow.tools.execution import execute_tool
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
        # [FIX] Require BOTH name and arguments to avoid false positives (e.g. random JSON with "name" key)
        args_container = data.get("arguments") or data.get("args") or data.get("input")
        
        if not tool_name or args_container is None:
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
        """从最近的 assistant 消息中解析 ToolCall / Action"""
        content = None
        for msg in reversed(messages):
            if isinstance(msg, Message) and msg.role == "assistant":
                content = msg.content
                break
            if not isinstance(msg, Message):
                content = str(msg)
                break

        if content is None:
            logger.debug("📭 [{}] 未检测到可解析的 assistant 消息", self.name)
            return None

        extracted = self._extract_tool_call_from_marked(content)
        if extracted:
            return extracted

        match = self.ACTION_PATTERN.search(content)
        if not match:
            logger.debug("📭 [{}] 未检测到 Action，跳过", self.name)
            return None

        tool_name = match.group(1).strip().lower()
        tool_input = match.group(2).strip()
        return tool_name, tool_input

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

            # Policy guardrail
            guard_error = self.policy.validate_call(self.state_manager.get(), tool_name, tool_input)
            if guard_error:
                return self._normalize_tool_result(tool_name, None, error=guard_error)

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
                            should_write = True
                            output_val = result
                            if isinstance(result, ToolResult):
                                if not result.ok:
                                    should_write = False
                                else:
                                    output_val = result.output

                            if should_write:
                                self.state_manager.update({tool_node.output_key: output_val})
                                logger.debug("💾 [{}] ToolNode '{}' output written to key '{}'",
                                             self.name, tool_name, tool_node.output_key)
                    else:
                        result = await self._run_tool(tool, parsed_input)

                    # Normalize Result
                    tool_result = self._coerce_tool_result(result)
                    if tool_result.ok:
                        output_error = self._validate_tool_output(tool, tool_result.output)
                        if output_error:
                            logger.warning(
                                "⚠️ [{}] Tool '{}' output mismatch schema: {}",
                                self.name,
                                tool_name,
                                output_error,
                            )
                            if self.strict_output_validation:
                                tool_result = ToolResult(ok=False, error=output_error)
                    observation = self._normalize_tool_result(tool_name, tool_result, error=tool_result.error)
                    retryable = tool_result.retryable and not tool_result.ok
                    ok = tool_result.ok
                    error_msg = tool_result.error
                    trace_result = tool_result.output

                    trace_emit("tool_result", {
                        "node": self.name,
                        "tool": tool_name,
                        "ok": ok,
                        "error": error_msg,
                        "result": self._safe_trace_payload(trace_result)
                    })

                    if not retryable:
                        return observation
                    if attempts <= self.max_retries:
                        logger.warning(
                            "⚠️ [{}] Tool '{}' failed (attempt {}/{}), retrying... Error: {}",
                            self.name, tool_name, attempts, self.max_retries, error_msg,
                        )

                except ToolError as e:
                    logger.warning("⚠️ [{}] 工具异常: {}", self.name, e)
                    observation = self._normalize_tool_result(tool_name, None, error=f"{e.code}: {e}")
                    retryable = e.retryable
                    trace_emit("tool_result", {
                        "node": self.name,
                        "tool": tool_name,
                        "ok": False,
                        "error": f"{e.code}: {e}",
                    })
                    if not retryable:
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
                    return observation

                if attempts > self.max_retries:
                    return observation

                await asyncio.sleep(self.retry_backoff * attempts)

    async def update_async(self) -> Status:
        state = self.state_manager.get()

        if not state.messages:
            return Status.SUCCESS

        # 1. Parse Action
        action = self._parse_latest_action(state.messages)
        if not action:
            return Status.SUCCESS
        
        tool_name, tool_input = action

        # 2. Execute Action
        observation = await self._execute_action(tool_name, tool_input)

        # 3. Update State
        self.state_manager.update({"messages": [observation]})
        return Status.SUCCESS




class IsFinalAnswer(Behaviour):
    """
    条件节点：检查是否有 Final Answer。

    - 有 Final Answer → SUCCESS
    - 无 Final Answer → FAILURE
    """

    FINAL_ANSWER_PATTERN = re.compile(
        r"Final Answer:\s*(.+)",
        re.IGNORECASE | re.DOTALL
    )

    def __init__(self, name: str = "IsFinalAnswer", max_rounds: int = 10):
        super().__init__(name)
        self.max_rounds = max_rounds
        self.state_manager = None

    def update(self) -> Status:
        if self.state_manager is None:
            logger.error("❌ [{}] state_manager 未注入", self.name)
            return Status.FAILURE

        state = self.state_manager.get()

        if state.round >= self.max_rounds:
            logger.warning("⚠️ [{}] 达到最大轮数 ({}), 强制停止", self.name, self.max_rounds)
            self.state_manager.update({"final_answer": "[MAX_ROUNDS_EXCEEDED]"})
            return Status.SUCCESS

        final_answer = self._extract_final_answer(state.messages)

        if final_answer:
            logger.info(
                "✅ [{}] 检测到 Final Answer: {}...",
                self.name,
                final_answer[:50] if len(final_answer) > 50 else final_answer,
            )
            self.state_manager.update({"final_answer": final_answer})
            return Status.SUCCESS

        logger.debug(
            "🔄 [{}] 未检测到 Final Answer，继续下一轮 (Round {}/{})",
            self.name,
            state.round,
            self.max_rounds,
        )
        return Status.FAILURE

    def _extract_final_answer(self, messages: List[Message]) -> Optional[str]:
        if not messages:
            return None

        # Check the last message content
        last_msg = messages[-1]
        content = last_msg.content if isinstance(last_msg, Message) else str(last_msg)
        
        match = self.FINAL_ANSWER_PATTERN.search(content)
        if match:
            return match.group(1).strip()
        return None
