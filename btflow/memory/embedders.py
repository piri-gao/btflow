import os
from typing import Callable, List, Optional

from btflow.core.logging import logger


class GeminiEmbedder:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        try:
            from google import genai
            from google.genai import types
        except ImportError as e:
            raise RuntimeError(
                "google-genai package not installed. Run: pip install google-genai"
            ) from e

        key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("Gemini API key not found (GOOGLE_API_KEY/GEMINI_API_KEY)")

        resolved_base_url = base_url or os.getenv("EMBEDDING_BASE_URL") or os.getenv("BASE_URL")
        http_options = {"base_url": resolved_base_url} if resolved_base_url else None

        self._types = types
        self._client = genai.Client(api_key=key, http_options=http_options)
        self.model = model or os.getenv("GEMINI_EMBED_MODEL") or os.getenv("EMBEDDING_MODEL") or "text-embedding-004"

    def __call__(self, text: str) -> List[float]:
        response = self._client.models.embed_content(model=self.model, contents=text)
        embeddings = getattr(response, "embeddings", None)
        if embeddings:
            first = embeddings[0]
            values = getattr(first, "values", None)
            if values is not None:
                return list(values)
        return []


class OpenAIEmbedder:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
        if not key:
            raise RuntimeError("OpenAI API key not found (OPENAI_API_KEY/API_KEY)")

        resolved_base_url = base_url or os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE") or os.getenv("BASE_URL")

        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=key, base_url=resolved_base_url)
            self._legacy = False
        except Exception:
            import openai
            openai.api_key = key
            if resolved_base_url:
                openai.base_url = resolved_base_url
            self._client = openai
            self._legacy = True

        self.model = model or os.getenv("OPENAI_EMBED_MODEL") or os.getenv("EMBEDDING_MODEL") or "text-embedding-3-small"

    def __call__(self, text: str) -> List[float]:
        if self._legacy:
            response = self._client.Embedding.create(model=self.model, input=text)
            data = response.get("data") if isinstance(response, dict) else None
            if data:
                return list(data[0].get("embedding") or [])
            return []

        response = self._client.embeddings.create(model=self.model, input=text)
        if hasattr(response, "data") and response.data:
            return list(response.data[0].embedding)
        return []


def resolve_embedder(
    preference: Optional[List[str]] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Optional[Callable[[str], List[float]]]:
    order = preference or ["gemini", "openai"]

    for name in order:
        if name == "gemini":
            if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
                try:
                    return GeminiEmbedder(api_key=None, base_url=base_url, model=model)
                except Exception as e:
                    logger.warning("⚠️ [Embedder] Gemini init failed: {}", e)
        elif name == "openai":
            if os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY"):
                try:
                    return OpenAIEmbedder(api_key=None, base_url=base_url, model=model)
                except Exception as e:
                    logger.warning("⚠️ [Embedder] OpenAI init failed: {}", e)

    return None


__all__ = ["GeminiEmbedder", "OpenAIEmbedder", "resolve_embedder"]
