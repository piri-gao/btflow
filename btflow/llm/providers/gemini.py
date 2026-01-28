import asyncio
import os
from typing import Optional

from google import genai
from google.genai import types

from btflow.core.logging import logger
from btflow.llm.base import LLMResponse


class GeminiProvider:
    """Thin wrapper around google-genai for async content generation."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        self.base_url = base_url or os.getenv("BASE_URL")
        
        if not self.api_key:
            logger.warning("⚠️ Gemini API key not found in env (GOOGLE_API_KEY/GEMINI_API_KEY)")
            
        http_options = None
        if self.base_url:
            logger.debug(f"🔌 [GeminiProvider] Using custom Base URL: {self.base_url}")
            http_options = types.HttpOptions(base_url=self.base_url)
            
        self.client = genai.Client(api_key=self.api_key, http_options=http_options)

    async def generate_text(
        self,
        prompt: str,
        model: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.95,
        top_k: int = 40,
        timeout: float = 60.0,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[object] = None,
        strict_tools: bool = False,
    ):
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
        )
        response = await asyncio.wait_for(
            self.client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            ),
            timeout=timeout,
        )
        return LLMResponse(text=response.text, raw=response)
