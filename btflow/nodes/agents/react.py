import asyncio
import json
import re
from typing import Dict, List, Optional, Any

from py_trees.common import Status
from py_trees.behaviour import Behaviour

from btflow.core.behaviour import AsyncBehaviour
from btflow.core.logging import logger
from btflow.tools import Tool
from btflow.tools.registry import ToolRegistry
from btflow.tools.base import ToolError, ToolResult
from btflow.llm import LLMProvider, GeminiProvider


from btflow.messages import Message, human, ai, tool
from btflow.context.builder import ContextBuilder

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
        tools_description: str = ""
    ):
        super().__init__(name)
        self.model = model
        self.tools_description = tools_description
        self._uses_default_prompt = system_prompt is None
        self.system_prompt = system_prompt or self._get_default_prompt()
        self.provider = provider or GeminiProvider()
        
        # Internal context builder (tools are embedded in system prompt)
        self.context_builder = ContextBuilder(
            system_prompt=self.system_prompt,
            # We can inject memory here later
        )

    def _get_default_prompt(self, dynamic_tools_desc: str = "") -> str:
        description = dynamic_tools_desc or self.tools_description
        tools_section = f"\nAvailable tools:\n{description}" if description else "No tools available."

        return f"""You are a helpful assistant that can use tools to answer questions.

You must follow this EXACT format:

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
3. After seeing an Observation, continue with another "Thought:"
4. Only use "Final Answer:" when you have the complete answer

Always think step by step."""

    def _messages_to_prompt(self, messages: List[Message]) -> str:
        """Convert structured messages to ReAct-style string prompt."""
        # Simple serialization for text-based completion models
        # Future: Use chat API if provider supports it
        lines = []
        for msg in messages:
            if msg.role == "system":
                # System prompt involves instructions
                lines.append(f"System: {msg.content}")
            elif msg.role == "user":
                lines.append(f"User: {msg.content}")
            elif msg.role == "assistant":
                lines.append(f"Assistant: {msg.content}")
            elif msg.role == "tool":
                lines.append(f"Observation: {msg.content}")
            else:
                lines.append(f"{msg.role}: {msg.content}")
        return "\n".join(lines)

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
                      self.context_builder.system_prompt = self._get_default_prompt(tools_desc)

            logger.debug("📋 [{}] State dump: messages_count={}, task={}", self.name, len(messages), task)

            if not messages and task:
                logger.info("🎯 [{}] Initializing conversation with task: {}", self.name, task)
                # Initialize with HumanMessage
                initial_msg = human(f"User Question: {task}")
                messages = [initial_msg]
                self.state_manager.update({"messages": messages})

            if not messages:
                logger.warning("⚠️ [{}] No messages and no task, cannot call LLM", self.name)
                return Status.FAILURE

            # Build full context (System + Tools + History)
            full_messages = self.context_builder.build(messages)
            
            # Serialize to prompt string
            # Note: Since ReAct prompt template is complex and partly in system prompt,
            # ContextBuilder puts system prompt at the beginning.
            # We just join them for now.
            # TODO: Update LLMProvider to support List[Message] natively.
            prompt_content = self._messages_to_prompt(full_messages)

            logger.debug("🤖 [{}] 调用 LLM ({})...", self.name, self.model)
            # logger.debug("Prompt:\n{}", prompt_content)

            # Only verify system instruction logic for providers that separate it
            # But here we embedded it in prompt_content for safety via ContextBuilder
            # For providers taking system_instruction sep, maybe redundant but safe.
            
            response = await self.provider.generate_text(
                prompt_content,
                model=self.model,
                # context_builder already added system prompt to messages
                # system_instruction=None, 
                temperature=0.7,
                timeout=60.0,
            )

            content = response.text.strip()

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
            return Status.FAILURE
        except Exception as e:
            logger.error("🔥 [{}] Gemini 调用失败: {}", self.name, e)
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
    ):
        super().__init__(name)
        self.tools: Dict[str, Tool] = {}
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.observation_format = observation_format
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
            if hasattr(child, "tool"):
                self.register_tool(child.tool)

        if hasattr(self, "state_manager") and self.state_manager:
            desc = self.get_tools_description()
            schema = self.get_tools_schema()
            logger.info("🔧 [{}] Updating state.tools_desc with {} tools", self.name, len(self.tools))
            self.state_manager.update({"tools_desc": desc, "tools_schema": schema})

    def register_tool(self, tool: Tool):
        self.tools[tool.name.lower()] = tool
        logger.debug("🔧 [{}] 注册工具: {}", self.name, tool.name)

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
                schema.append(tool.spec().to_dict())
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
        elif isinstance(result, str):
            content = result
        else:
            content = json.dumps(payload, ensure_ascii=True)
            
        return tool(content=content, name=tool_name)

    def _parse_tool_input(self, tool: Tool, raw_input: str) -> tuple[Any, Optional[str]]:
        schema = getattr(tool, "input_schema", None) or {"type": "string"}
        schema_type = schema.get("type", "string")

        if schema_type == "string":
            return raw_input, None

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

    async def update_async(self) -> Status:
        state = self.state_manager.get()

        if not state.messages:
            return Status.SUCCESS

        # Find the most recent assistant message to parse Action/Input
        content = None
        for msg in reversed(state.messages):
            if isinstance(msg, Message) and msg.role == "assistant":
                content = msg.content
                break
            if not isinstance(msg, Message):
                content = str(msg)
                break

        if content is None:
            logger.debug("📭 [{}] 未检测到可解析的 assistant 消息", self.name)
            return Status.SUCCESS

        match = self.ACTION_PATTERN.search(content)

        if not match:
            logger.debug("📭 [{}] 未检测到 Action，跳过", self.name)
            return Status.SUCCESS

        tool_name = match.group(1).strip().lower()
        tool_input = match.group(2).strip()

        logger.info("⚙️ [{}] 执行 Action: {} Input: {}", self.name, tool_name, tool_input)

        tool = self.tools.get(tool_name)

        if tool:
            parsed_input, input_error = self._parse_tool_input(tool, tool_input)
            if input_error:
                observation = self._normalize_tool_result(tool_name, None, error=input_error)
            else:
                attempts = 0
                while True:
                    attempts += 1
                    try:
                        result = tool.run(parsed_input)
                        if isinstance(result, ToolResult):
                            observation = self._normalize_tool_result(tool_name, result, error=result.error)
                            retryable = result.retryable and not result.ok
                        else:
                            observation = self._normalize_tool_result(tool_name, result, error=None)
                            retryable = False
                    except ToolError as e:
                        logger.warning("⚠️ [{}] 工具异常: {}", self.name, e)
                        observation = self._normalize_tool_result(tool_name, None, error=f"{e.code}: {e}")
                        retryable = e.retryable
                    except Exception as e:
                        logger.warning("⚠️ [{}] 工具执行失败: {}", self.name, e)
                        observation = self._normalize_tool_result(
                            tool_name, None, error=f"tool_error: {e}"
                        )
                        retryable = False

                    if not retryable or attempts > self.max_retries:
                        break
                    await asyncio.sleep(self.retry_backoff * attempts)
        else:
            logger.warning("⚠️ [{}] 未知工具: {}", self.name, tool_name)
            observation = self._normalize_tool_result(
                tool_name,
                None,
                error=f"tool_not_found: Tool '{tool_name}' not found. Available tools: {list(self.tools.keys())}",
            )

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
