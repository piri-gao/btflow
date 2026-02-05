import asyncio
import json
import os
from typing import List, Optional

from py_trees.common import Status

from btflow.core.behaviour import AsyncBehaviour
from btflow.core.logging import logger
from btflow.core.trace import emit as trace_emit
from btflow.core.trace import span
from btflow.llm import LLMProvider, MessageChunk
from btflow.messages import Message, human, messages_to_prompt
from btflow.messages.formatting import message_to_text
from btflow.memory import Memory
from btflow.context import ContextBuilder, ContextBuilderProtocol


DEFAULT_REACT_PROMPT = """You are a helpful assistant that can use tools to answer questions.

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

IMPORTANT RULES:
1. Always start with "Thought:" to explain your reasoning
2. Use EXACT tool names as shown in the available tools list
3. ToolCall must be valid JSON
4. After seeing an Observation, continue with another "Thought:"
5. Only use "Final Answer:" when you have the complete answer

Always think step by step."""


class AgentLLMNode(AsyncBehaviour):
    """
    Agent LLM node.

    Reads state.messages/task, builds context, calls the LLM, and appends
    the assistant response back to state.messages.
    """

    def __init__(
        self,
        name: str = "AgentLLM",
        model: str = "gemini-2.5-flash",
        provider: Optional[LLMProvider] = None,
        system_prompt: Optional[str] = None,
        tools_description: str = "",
        memory: Optional[Memory] = None,
        memory_top_k: int = 5,
        structured_tool_calls: bool = True,
        strict_tool_calls: bool = False,
        stream: bool = False,
        streaming_output_key: str = "streaming_output",
        context_builder: Optional[ContextBuilderProtocol] = None,
    ):
        super().__init__(name)
        self.model = model
        self.tools_description = tools_description
        self._uses_default_prompt = system_prompt is None or system_prompt == ""
        self.system_prompt = system_prompt if not self._uses_default_prompt else DEFAULT_REACT_PROMPT
        self.provider = provider or LLMProvider.default()
        self.structured_tool_calls = structured_tool_calls
        self.strict_tool_calls = strict_tool_calls
        self.stream = stream
        self.streaming_output_key = streaming_output_key

        if context_builder is None:
            self.context_builder = ContextBuilder(
                system_prompt=self.system_prompt,
                tools_desc=self.tools_description,
                memory=memory,
                memory_top_k=memory_top_k,
            )
        else:
            self.context_builder = context_builder
            if hasattr(self.context_builder, "system_prompt"):
                self.context_builder.system_prompt = self.system_prompt

    async def update_async(self) -> Status:
        try:
            state = self.state_manager.get()
            messages: List[Message] = list(state.messages) if hasattr(state, "messages") else []
            task = getattr(state, "task", None)

            tools_desc = getattr(state, "tools_desc", "")
            if tools_desc:
                self.tools_description = tools_desc
            if hasattr(self.context_builder, "tools_desc"):
                self.context_builder.tools_desc = tools_desc

            logger.debug("📋 [{}] State dump: messages_count={}, task={}", self.name, len(messages), task)

            if not messages and task:
                initial_msg = human(f"User Question: {task}")
                messages = [initial_msg]
                self.state_manager.update({"messages": messages})
                state = self.state_manager.get()

            if not messages:
                logger.warning("⚠️ [{}] No messages and no task, cannot call LLM", self.name)
                return Status.FAILURE

            full_messages = self.context_builder.build(
                state,
                tools_schema=getattr(state, "tools_schema", None),
            )
            prompt_content = messages_to_prompt(full_messages)

            tools_schema = getattr(state, "tools_schema", None)
            with span("llm_call", model=self.model):
                trace_emit("llm_call", {
                    "node": self.name,
                    "model": self.model,
                    "messages": len(full_messages),
                })

                response_msg = None
                content = ""
                tool_calls = None

                if self.stream:
                    if self.streaming_output_key:
                        self.state_manager.update({self.streaming_output_key: ""})
                    parts = []
                    try:
                        async for chunk in self.provider.generate_stream(
                            prompt_content,
                            model=self.model,
                            temperature=0.7,
                            timeout=60.0,
                            tools=tools_schema if self.structured_tool_calls else None,
                            strict_tools=self.strict_tool_calls,
                        ):
                            if isinstance(chunk, MessageChunk):
                                if chunk.text:
                                    parts.append(chunk.text)
                                    trace_emit("llm_token", {
                                        "node": self.name,
                                        "token": chunk.text,
                                        "full_content": "".join(parts)
                                    })
                                    if self.streaming_output_key:
                                        self.state_manager.update(
                                            {self.streaming_output_key: "".join(parts)}
                                        )
                                if chunk.tool_calls:
                                    tool_calls = chunk.tool_calls
                    except NotImplementedError:
                        response_msg = await self.provider.generate_text(
                            prompt_content,
                            model=self.model,
                            temperature=0.7,
                            timeout=60.0,
                            tools=tools_schema if self.structured_tool_calls else None,
                            strict_tools=self.strict_tool_calls,
                        )
                    if response_msg is None:
                        content = "".join(parts)
                        response_msg = Message(
                            role="assistant",
                            content=content,
                            tool_calls=tool_calls,
                        )
                    else:
                        content = message_to_text(response_msg)
                else:
                    response_msg = await self.provider.generate_text(
                        prompt_content,
                        model=self.model,
                        temperature=0.7,
                        timeout=60.0,
                        tools=tools_schema if self.structured_tool_calls else None,
                        strict_tools=self.strict_tool_calls,
                    )
                    content = message_to_text(response_msg)

                if response_msg and hasattr(response_msg, "tool_calls") and response_msg.tool_calls:
                    tool_call = response_msg.tool_calls[0]
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
                    response_msg.content = content

                trace_emit("llm_response", {
                    "node": self.name,
                    "model": self.model,
                    "content_len": len(content),
                })

            if not content:
                logger.warning("⚠️ [{}] LLM 返回空响应", self.name)
                return Status.FAILURE

            rounds = getattr(state, "rounds", 0)
            self.state_manager.update({
                "messages": [response_msg],
                "rounds": rounds + 1
            })

            log_limit = int(os.getenv("BTFLOW_LOG_MAX_LEN", "200") or "200")
            if log_limit <= 0:
                preview = content
            elif len(content) > log_limit:
                preview = content[:log_limit] + "..."
            else:
                preview = content
            logger.info("💭 [{}] Round {} 响应:\n{}", self.name, rounds + 1, preview)
            return Status.SUCCESS

        except asyncio.TimeoutError:
            logger.warning("⏰ [{}] 请求超时", self.name)
            trace_emit("llm_error", {"node": self.name, "model": self.model, "error": "timeout"})
            return Status.FAILURE
        except Exception as e:
            logger.error("🔥 [{}] LLM 调用失败: {}", self.name, e)
            trace_emit("llm_error", {"node": self.name, "model": self.model, "error": str(e)})
            return Status.FAILURE


__all__ = ["AgentLLMNode", "DEFAULT_REACT_PROMPT"]
