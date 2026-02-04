import asyncio
from typing import List, Dict, Any, Optional
from duckduckgo_search import DDGS
from btflow.tools.base import Tool
from btflow.core.logging import logger

class DuckDuckGoSearchTool(Tool):
    """
    DuckDuckGo web search (no API key required).
    """
    name = "duckduckgo_search"
    description = (
        "Search the web for real-time information. "
        "Useful for current events, news, and general knowledge. "
        "Input should be a search query string."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 5
            }
        },
        "required": ["query"]
    }

    async def run(self, query: str, max_results: int = 5) -> str:
        """Execute search via DDG."""
        logger.debug(f"🔍 [DuckDuckGo] Searching for: {query}")
        
        try:
            # Use run_in_executor if the library is not async, 
            # but ddgs has a synchronous and asynchronous version. 
            # We'll use the sync one within an executor for safety if preferred,
            # or just use the async version if available.
            # duckduckgo_search 6.x+ has DDGS context manager.
            
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, self._sync_search, query, max_results)
            
            if not results:
                return "No results found for this query."

            formatted_results = []
            for i, r in enumerate(results, 1):
                formatted_results.append(
                    f"[{i}] {r.get('title')}\n"
                    f"URL: {r.get('href')}\n"
                    f"Snippet: {r.get('body')}\n"
                )
            
            return "\n".join(formatted_results)
            
        except Exception as e:
            logger.error(f"❌ [DuckDuckGo] Search failed: {e}")
            return f"Error performing search: {str(e)}"

    def _sync_search(self, query: str, max_results: int) -> List[Dict[str, str]]:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
