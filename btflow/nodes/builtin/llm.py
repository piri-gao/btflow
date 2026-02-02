import asyncio
from typing import Any, List, Optional

from py_trees.common import Status

from btflow.core.behaviour import AsyncBehaviour
from btflow.core.logging import logger
from btflow.llm import LLMProvider, MessageChunk
from btflow.messages import Message, ai
from btflow.messages.formatting import messages_to_prompt, message_to_text


class LLMNode(AsyncBehaviour):
    """
    Generic LLM node using an injected provider.
    """

    def __init__(
        self,
        name: str,
        provider: Optional[LLMProvider] = None,
        model: str = "gemini-2.5-flash",
        system_prompt: str = "You are a helpful AI assistant.",
        messages_key: str = "messages",
        output_key: str = "messages",
        assistant_prefix: str = "Assistant",
        output_as_messages: bool = False,
        step_key: Optional[str] = None,
        stream: bool = False,
        streaming_output_key: str = "streaming_output",
    ):
        super().__init__(name)
        self.provider = provider or LLMProvider.default()
        self.model = model
        self.system_prompt = system_prompt
        self.messages_key = messages_key
        self.output_key = output_key
        self.assistant_prefix = assistant_prefix
        self.output_as_messages = output_as_messages
        self.step_key = step_key
        self.stream = stream
        self.streaming_output_key = streaming_output_key

    async def update_async(self) -> Status:
        try:
            state = self.state_manager.get()
            messages = getattr(state, self.messages_key, None)
            prompt_content = self._build_prompt(messages)

            response = None
            content = ""
            if self.stream:
                if self.streaming_output_key:
                    self.state_manager.update({self.streaming_output_key: ""})
                parts: List[str] = []
                try:
                    async for chunk in self.provider.generate_stream(
                        prompt_content,
                        model=self.model,
                        system_instruction=self.system_prompt,
                        temperature=0.7,
                        timeout=30.0,
                    ):
                        if isinstance(chunk, MessageChunk):
                            text = chunk.text or ""
                        else:
                            text = getattr(chunk, "text", "") or ""
                        if text:
                            parts.append(text)
                            if self.streaming_output_key:
                                self.state_manager.update(
                                    {self.streaming_output_key: "".join(parts)}
                                )
                except NotImplementedError:
                    response = await self.provider.generate_text(
                        prompt_content,
                        model=self.model,
                        system_instruction=self.system_prompt,
                        temperature=0.7,
                        timeout=30.0,
                    )
                if response is None:
                    content = "".join(parts)
                else:
                    content = message_to_text(response)
            else:
                response = await self.provider.generate_text(
                    prompt_content,
                    model=self.model,
                    system_instruction=self.system_prompt,
                    temperature=0.7,
                    timeout=30.0,
                )
                content = message_to_text(response)

            updates = {}
            if self.output_key:
                if self.output_key == self.messages_key and isinstance(messages, list):
                    if self.output_as_messages:
                        updates[self.output_key] = [ai(content)]
                    else:
                        updates[self.output_key] = [f"{self.assistant_prefix}: {content}"]
                else:
                    updates[self.output_key] = content
            if self.step_key:
                updates[self.step_key] = 1

            if updates:
                self.state_manager.update(updates)

            return Status.SUCCESS
        except asyncio.TimeoutError:
            logger.warning("⏰ [{}] 请求超时", self.name)
            return Status.FAILURE
        except Exception as e:
            logger.error("🔥 [{}] LLM 调用失败: {}", self.name, e)
            self.feedback_message = str(e)
            return Status.FAILURE

    def _build_prompt(self, messages: Any) -> str:
        if messages is None:
            return ""
        if isinstance(messages, list):
            if messages and isinstance(messages[0], Message):
                return messages_to_prompt(messages)
            return "\n".join([message_to_text(m) for m in messages])
        return message_to_text(messages)


__all__ = ["LLMNode"]
