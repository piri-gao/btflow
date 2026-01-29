"""
HTTP Tool - Make HTTP requests.
"""
import asyncio
import json
from typing import Any, Optional, Dict
import aiohttp

from btflow.tools import Tool


class HTTPTool(Tool):
    """
    Make HTTP requests to external APIs.
    
    Supports GET, POST, PUT, DELETE methods with JSON payloads.
    """
    
    name = "http_request"
    description = "Make HTTP requests to APIs. Supports GET, POST, PUT, DELETE methods."
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to request"
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "DELETE"],
                "description": "HTTP method (default: GET)"
            },
            "headers": {
                "type": "object",
                "description": "Optional HTTP headers"
            },
            "body": {
                "type": "object",
                "description": "Optional JSON body for POST/PUT requests"
            }
        },
        "required": ["url"]
    }
    output_schema = {"type": "string"}

    def __init__(
        self,
        timeout: float = 30.0,
        max_response_length: int = 50000,
        default_headers: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize HTTP tool.
        
        Args:
            timeout: Request timeout in seconds
            max_response_length: Maximum response body length
            default_headers: Default headers to include in all requests
        """
        self.timeout = timeout
        self.max_response_length = max_response_length
        self.default_headers = default_headers or {}

    async def run(
        self,
        url: str = None,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """Make an HTTP request."""
        # Handle input from various formats
        if url is None:
            url = kwargs.get("input", "")
        
        if not url:
            return "Error: No URL provided"
        
        method = method.upper()
        merged_headers = {**self.default_headers, **(headers or {})}
        
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                request_kwargs = {"headers": merged_headers}
                
                if body and method in ("POST", "PUT"):
                    request_kwargs["json"] = body
                
                async with session.request(method, url, **request_kwargs) as response:
                    status = response.status
                    content_type = response.headers.get("Content-Type", "")
                    
                    # Try to parse as JSON first
                    if "application/json" in content_type:
                        try:
                            data = await response.json()
                            text = json.dumps(data, ensure_ascii=False, indent=2)
                        except:
                            text = await response.text()
                    else:
                        text = await response.text()
                    
                    # Truncate if too long
                    if len(text) > self.max_response_length:
                        text = text[:self.max_response_length] + f"\n... (truncated)"
                    
                    return f"[HTTP {status}]\n{text}"
                    
        except asyncio.TimeoutError:
            return f"Error: Request timed out after {self.timeout}s"
        except aiohttp.ClientError as e:
            return f"Error: {type(e).__name__}: {e}"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"
