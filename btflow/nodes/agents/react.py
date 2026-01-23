import asyncio
import json
import re
from typing import Dict, List, Optional, Any

from py_trees.common import Status
from py_trees.behaviour import Behaviour

from btflow.core.behaviour import AsyncBehaviour
from btflow.core.logging import logger
from btflow.tools import Tool
from btflow.llm import GeminiProvider


class ReActGeminiNode(AsyncBehaviour):
    """
    ReAct 推理节点：调用 Gemini 进行思考。

    每次 tick 都会调用 LLM，由 Repeat 控制循环。
    """

    def __init__(
        self,
        name: str = "ReActGemini",
        model: str = "gemini-2.5-flash",
        system_prompt: Optional[str] = None,
        tools_description: str = ""
    ):
        super().__init__(name)
        self.model = model
        self.tools_description = tools_description
        self.system_prompt = system_prompt or self._get_default_prompt()
        self.provider = GeminiProvider()

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

    async def update_async(self) -> Status:
        """调用 Gemini 进行 ReAct 推理"""
        try:
            state = self.state_manager.get()
            messages = list(state.messages) if hasattr(state, "messages") else []
            task = getattr(state, "task", None)

            tools_desc = getattr(state, "tools_desc", "")

            logger.debug("📋 [{}] State dump: messages={}, task={}", self.name, messages, task)

            if not messages and task:
                logger.info("🎯 [{}] Initializing conversation with task: {}", self.name, task)
                messages = [f"User Question: {task}"]
                self.state_manager.update({"messages": messages})

            if not messages:
                logger.warning("⚠️ [{}] No messages and no task, cannot call LLM", self.name)
                return Status.FAILURE

            prompt_content = "\n".join(messages)

            logger.debug("🤖 [{}] 调用 Gemini ({})...", self.name, self.model)

            system_instruction = self.system_prompt
            if not system_instruction or "Available tools:" not in system_instruction:
                system_instruction = self._get_default_prompt(tools_desc)

            response = await self.provider.generate_text(
                prompt_content,
                model=self.model,
                system_instruction=system_instruction,
                temperature=0.7,
                timeout=60.0,
            )

            content = response.text.strip()

            if not content:
                logger.warning("⚠️ [{}] LLM 返回空响应", self.name)
                return Status.FAILURE

            self.state_manager.update({
                "messages": [content],
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

    def __init__(self, name: str = "ToolExecutor", tools: Optional[List[Tool]] = None):
        super().__init__(name)
        self.tools: Dict[str, Tool] = {}
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

    def _normalize_tool_result(self, tool_name: str, result: Any, error: Optional[str]) -> str:
        if error:
            return f"Observation: {error}"

        if hasattr(result, "to_dict"):
            try:
                payload = result.to_dict()
            except Exception:
                payload = {"tool": tool_name, "ok": True, "output": str(result), "error": None}
            return f"Observation: {json.dumps(payload, ensure_ascii=True)}"

        if isinstance(result, str):
            return f"Observation: {result}"

        payload = {"tool": tool_name, "ok": True, "output": result, "error": None}
        return f"Observation: {json.dumps(payload, ensure_ascii=True)}"

    async def update_async(self) -> Status:
        state = self.state_manager.get()

        if not state.messages:
            return Status.SUCCESS

        last_msg = state.messages[-1]
        match = self.ACTION_PATTERN.search(last_msg)

        if not match:
            logger.debug("📭 [{}] 未检测到 Action，跳过", self.name)
            return Status.SUCCESS

        tool_name = match.group(1).strip().lower()
        tool_input = match.group(2).strip()

        logger.info("⚙️ [{}] 执行 Action: {} Input: {}", self.name, tool_name, tool_input)

        tool = self.tools.get(tool_name)

        if tool:
            try:
                result = tool.run(tool_input)
                observation = self._normalize_tool_result(tool_name, result, error=None)
            except Exception as e:
                logger.warning("⚠️ [{}] 工具执行失败: {}", self.name, e)
                observation = self._normalize_tool_result(
                    tool_name, None, error=f"Error executing {tool_name}: {e}"
                )
        else:
            logger.warning("⚠️ [{}] 未知工具: {}", self.name, tool_name)
            observation = self._normalize_tool_result(
                tool_name,
                None,
                error=f"Tool '{tool_name}' not found. Available tools: {list(self.tools.keys())}",
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

    def _extract_final_answer(self, messages: List[str]) -> Optional[str]:
        if not messages:
            return None

        last_msg = messages[-1]
        match = self.FINAL_ANSWER_PATTERN.search(last_msg)
        if match:
            return match.group(1).strip()
        return None
