import os
from typing import Optional, Any, List, Dict, AsyncIterator

from btflow.core.logging import logger
from btflow.llm.base import LLMProvider, MessageChunk
from btflow.messages import Message


class OpenAIProvider(LLMProvider):
    """Async OpenAI chat provider (requires openai package)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
    ):
        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise RuntimeError(
                "openai package not installed. Run: pip install openai"
            ) from e

        key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
        if not key:
            logger.warning("⚠️ OPENAI_API_KEY/API_KEY not found in env!")

        resolved_base_url = base_url or os.getenv("BASE_URL") or os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
        self.client = AsyncOpenAI(api_key=key, base_url=resolved_base_url, organization=organization)

    async def generate_text(
        self,
        prompt: Any,
        model: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.95,
        top_k: int = 40,
        timeout: float = 60.0,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[object] = None,
        strict_tools: bool = False,
        **kwargs
    ) -> Message:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        
        # Support string or list prompt (multimodal)
        messages.append({"role": "user", "content": prompt})

        tool_payload = None
        if tools:
            tool_payload = [
                {"type": "function", "function": t} if "type" not in t else t
                for t in tools
            ]
            if tool_choice is None:
                tool_choice = "required" if strict_tools else "auto"

        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            timeout=timeout,
            tools=tool_payload,
            tool_choice=tool_choice,
        )
        content = ""
        tool_calls = []

        if isinstance(response, str):
            content = response
        elif isinstance(response, dict):
            choices = response.get("choices") or []
            if choices:
                message = choices[0].get("message") or {}
                content = message.get("content") or ""
                for tc in message.get("tool_calls") or []:
                    fn = tc.get("function") or {}
                    name = fn.get("name")
                    arguments = fn.get("arguments")
                    if name:
                        tool_calls.append({"name": name, "arguments": arguments})
                if "function_call" in message:
                    fn = message.get("function_call") or {}
                    name = fn.get("name")
                    arguments = fn.get("arguments")
                    if name:
                        tool_calls.append({"name": name, "arguments": arguments})
            else:
                content = response.get("output_text") or response.get("text") or ""
        else:
            message = response.choices[0].message
            content = message.content or ""
            if getattr(message, "tool_calls", None):
                for tc in message.tool_calls:
                    fn = getattr(tc, "function", None)
                    if fn is not None:
                        tool_calls.append({"name": fn.name, "arguments": fn.arguments})
            if getattr(message, "function_call", None):
                fn = message.function_call
                tool_calls.append({"name": fn.name, "arguments": fn.arguments})
            
        return Message(
            role="assistant",
            content=content,
            tool_calls=tool_calls or None,
            metadata={"raw": response}
        )
    async def generate_stream(
        self,
        prompt: Any,
        model: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.95,
        top_k: int = 40,
        timeout: float = 60.0,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[object] = None,
        strict_tools: bool = False,
        **kwargs
    ) -> AsyncIterator[MessageChunk]:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        tool_payload = None
        if tools:
            tool_payload = [
                {"type": "function", "function": t} if "type" not in t else t
                for t in tools
            ]
            if tool_choice is None:
                tool_choice = "required" if strict_tools else "auto"

        stream = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            timeout=timeout,
            tools=tool_payload,
            tool_choice=tool_choice,
            stream=True,
        )

        async for chunk in stream:
            if not chunk.choices:
                continue
            
            delta = chunk.choices[0].delta
            text = delta.content or ""
            
            tool_calls = None
            if delta.tool_calls:
                tool_calls = []
                for tc in delta.tool_calls:
                    # In OpenAI streams, tool calls can be incremental. 
                    # For simplicity in ReAct context, we only emit if name/arguments are present.
                    # Or we could just pass the raw delta and let the node accumulate.
                    # But the schema expected by node is List[Dict[str, Any]].
                    fn = tc.function
                    if fn:
                        tool_calls.append({"name": fn.name, "arguments": fn.arguments, "index": tc.index})
            
            yield MessageChunk(text=text, tool_calls=tool_calls, raw=chunk)
