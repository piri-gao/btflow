import asyncio
import os
from typing import Optional, Any, AsyncIterator, List, Dict, Tuple

from btflow.core.logging import logger
from btflow.llm.base import LLMProvider, MessageChunk
from btflow.messages import Message


class GeminiProvider(LLMProvider):
    """Thin wrapper around google-genai for async content generation."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        try:
            from google import genai
            from google.genai import types
        except ImportError as e:
            raise RuntimeError(
                "google-genai package not installed. Run: pip install google-genai"
            ) from e

        self.api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY")
        self.base_url = base_url or os.getenv("BASE_URL")
        
        if not self.api_key:
            logger.warning("⚠️ Gemini API key not found in env (GOOGLE_API_KEY/GEMINI_API_KEY)")
            
        http_options = None
        if self.base_url:
            logger.debug(f"🔌 [GeminiProvider] Using custom Base URL: {self.base_url}")
            http_options = {"base_url": self.base_url}
            
        self._types = types
        self.client = genai.Client(api_key=self.api_key, http_options=http_options)

    def _get_field_names(self, cls: Any) -> set:
        fields = getattr(cls, "model_fields", None) or getattr(cls, "__fields__", None) or {}
        if isinstance(fields, dict):
            return set(fields.keys())
        return set()

    def _normalize_tool_schema(self, tool: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(tool, dict):
            return None

        if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
            return tool["function"]

        if "name" in tool:
            return tool

        return None

    def _build_function_declaration(self, name: str, description: str, parameters: Any) -> Any:
        fd_cls = self._types.FunctionDeclaration
        fields = self._get_field_names(fd_cls)
        kwargs: Dict[str, Any] = {"name": name, "description": description}

        if "parametersJsonSchema" in fields:
            kwargs["parametersJsonSchema"] = parameters
        elif "parameters_json_schema" in fields:
            kwargs["parameters_json_schema"] = parameters
        elif "parameters" in fields:
            kwargs["parameters"] = parameters

        return fd_cls(**kwargs)

    def _build_tools_config(
        self,
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: Optional[Any],
        strict_tools: bool,
    ) -> Tuple[Optional[List[Any]], Optional[Any]]:
        if not tools:
            return None, None

        function_decls = []
        for tool in tools:
            spec = self._normalize_tool_schema(tool)
            if not spec:
                continue
            name = spec.get("name")
            if not name:
                continue
            description = spec.get("description") or ""
            parameters = spec.get("parameters") or spec.get("parameters_json_schema") or {
                "type": "object",
                "properties": {},
            }
            try:
                function_decls.append(self._build_function_declaration(name, description, parameters))
            except Exception:
                # Fallback: skip invalid tool schema
                continue

        if not function_decls:
            return None, None

        tool_fields = self._get_field_names(self._types.Tool)
        if "functionDeclarations" in tool_fields:
            tools_payload = [self._types.Tool(functionDeclarations=function_decls)]
        else:
            tools_payload = [self._types.Tool(function_declarations=function_decls)]

        mode = None
        allowed = None
        if isinstance(tool_choice, str):
            choice = tool_choice.lower()
            if choice in ("none", "no", "disable"):
                mode = "NONE"
            elif choice in ("required", "any", "always"):
                mode = "ANY"
        elif isinstance(tool_choice, dict):
            name = tool_choice.get("name")
            if not name and isinstance(tool_choice.get("function"), dict):
                name = tool_choice["function"].get("name")
            if not name:
                name = tool_choice.get("tool")
            if name:
                allowed = [name]

        if strict_tools and mode is None:
            mode = "ANY"

        tool_config = None
        if mode or allowed:
            if mode is None:
                mode = "AUTO"
            fcc_fields = self._get_field_names(self._types.FunctionCallingConfig)
            fcc_kwargs: Dict[str, Any] = {"mode": mode}
            if allowed is not None:
                if "allowedFunctionNames" in fcc_fields:
                    fcc_kwargs["allowedFunctionNames"] = allowed
                else:
                    fcc_kwargs["allowed_function_names"] = allowed
            fcc = self._types.FunctionCallingConfig(**fcc_kwargs)

            tc_fields = self._get_field_names(self._types.ToolConfig)
            if "functionCallingConfig" in tc_fields:
                tool_config = self._types.ToolConfig(functionCallingConfig=fcc)
            else:
                tool_config = self._types.ToolConfig(function_calling_config=fcc)

        return tools_payload, tool_config

    async def generate_text(
        self,
        prompt: Any,
        model: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.95,
        top_k: int = 40,
        timeout: float = 60.0,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[object] = None,
        strict_tools: bool = False,
        **kwargs
    ) -> Message:
        tools_payload, tool_config = self._build_tools_config(tools, tool_choice, strict_tools)
        config_fields = self._get_field_names(self._types.GenerateContentConfig)
        config_kwargs: Dict[str, Any] = {
            "system_instruction": system_instruction,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "tools": tools_payload,
        }
        if tool_config is not None:
            if "toolConfig" in config_fields:
                config_kwargs["toolConfig"] = tool_config
            else:
                config_kwargs["tool_config"] = tool_config

        config = self._types.GenerateContentConfig(**config_kwargs)
        response = await asyncio.wait_for(
            self.client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            ),
            timeout=timeout,
        )
        tool_calls = None
        try:
            if hasattr(response, "function_calls") and response.function_calls:
                for tc in response.function_calls:
                    if tool_calls is None:
                        tool_calls = []
                    tool_calls.append({"name": tc.name, "arguments": tc.args})
            elif hasattr(response, "candidates") and response.candidates:
                first = response.candidates[0]
                if hasattr(first, "content") and hasattr(first.content, "parts"):
                    for part in first.content.parts:
                        if hasattr(part, "call"):
                            tc = part.call
                            if tool_calls is None:
                                tool_calls = []
                            tool_calls.append({"name": tc.name, "arguments": tc.args})
        except Exception:
            tool_calls = tool_calls
        return Message(
            role="assistant",
            content=response.text or "",
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
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[object] = None,
        strict_tools: bool = False,
        **kwargs
    ):
        tools_payload, tool_config = self._build_tools_config(tools, tool_choice, strict_tools)
        config_fields = self._get_field_names(self._types.GenerateContentConfig)
        config_kwargs: Dict[str, Any] = {
            "system_instruction": system_instruction,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "tools": tools_payload,
        }
        if tool_config is not None:
            if "toolConfig" in config_fields:
                config_kwargs["toolConfig"] = tool_config
            else:
                config_kwargs["tool_config"] = tool_config

        config = self._types.GenerateContentConfig(**config_kwargs)
        # Note: generate_content_stream returns an async generator directly, no await needed
        stream = self.client.aio.models.generate_content_stream(
            model=model,
            contents=prompt,
            config=config,
        )
        async for chunk in stream:
            text = getattr(chunk, "text", "") or ""
            
            tool_calls = None
            # Extract tool calls from Gemini chunk if present
            if hasattr(chunk, "function_calls") and chunk.function_calls:
                tool_calls = [{"name": tc.name, "arguments": tc.args} for tc in chunk.function_calls]
            elif hasattr(chunk, "candidates") and chunk.candidates:
                first = chunk.candidates[0]
                if hasattr(first, "content") and hasattr(first.content, "parts"):
                    for part in first.content.parts:
                        if hasattr(part, "call"):
                            tc = part.call
                            if tool_calls is None:
                                tool_calls = []
                            tool_calls.append({"name": tc.name, "arguments": tc.args})

            if not text and not tool_calls:
                continue
            yield MessageChunk(text=text, tool_calls=tool_calls, raw=chunk)
