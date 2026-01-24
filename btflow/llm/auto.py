import os
from typing import Optional

from btflow.llm import LLMProvider, GeminiProvider, OpenAIProvider, AnthropicProvider


class AutoProviderFactory:
    """Choose an available provider based on env vars."""

    def __init__(self, preference: Optional[list[str]] = None):
        # default order
        self.preference = preference or ["gemini", "openai", "anthropic"]

    def select(self) -> LLMProvider:
        for name in self.preference:
            if name == "gemini":
                if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
                    return GeminiProvider()
            elif name == "openai":
                if os.getenv("OPENAI_API_KEY"):
                    return OpenAIProvider()
            elif name == "anthropic":
                if os.getenv("ANTHROPIC_API_KEY"):
                    return AnthropicProvider()

        # Fallback: still return GeminiProvider (will warn if no key)
        return GeminiProvider()
