from btflow.llm.base import LLMProvider, MessageChunk
from btflow.llm.auto import AutoProviderFactory

__all__ = [
    "LLMProvider",
    "MessageChunk",
    "GeminiProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "AutoProviderFactory",
]


def _load_provider(name: str):
    from btflow.llm import providers
    if name == "GeminiProvider":
        return providers.GeminiProvider
    if name == "OpenAIProvider":
        return providers.OpenAIProvider
    if name == "AnthropicProvider":
        return providers.AnthropicProvider
    raise AttributeError(f"Unknown provider: {name}")


def __getattr__(name: str):
    if name in ("GeminiProvider", "OpenAIProvider", "AnthropicProvider"):
        try:
            return _load_provider(name)
        except ImportError as e:
            raise RuntimeError(
                f"{name} requires optional dependencies. "
                "Install provider SDK or the appropriate extra."
            ) from e
    raise AttributeError(f"module 'btflow.llm' has no attribute '{name}'")


def __dir__():
    return sorted(__all__)
