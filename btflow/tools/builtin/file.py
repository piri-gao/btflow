"""
File Tools - Read and write files.
"""
import asyncio
import os
from pathlib import Path
from typing import Optional

from btflow.tools.base import Tool


class FileReadTool(Tool):
    """
    Read contents of a file.
    """
    
    name = "read_file"
    description = "Read the contents of a file. Returns the file content as text."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to read"
            },
            "encoding": {
                "type": "string",
                "description": "File encoding (default: utf-8)"
            }
        },
        "required": ["path"]
    }
    output_schema = {"type": "string"}

    def __init__(
        self,
        max_file_size: int = 1_000_000,  # 1MB
        allowed_extensions: Optional[list] = None,
        base_path: Optional[str] = None,
    ):
        """
        Initialize file read tool.
        
        Args:
            max_file_size: Maximum file size in bytes
            allowed_extensions: List of allowed file extensions (None = all)
            base_path: Base path to restrict file access
        """
        self.max_file_size = max_file_size
        self.allowed_extensions = allowed_extensions
        self.base_path = Path(base_path) if base_path else None

    def _validate_path(self, path: str) -> tuple[Path, Optional[str]]:
        """Validate and resolve the file path."""
        try:
            file_path = Path(path).resolve()
            
            # Check base path restriction
            if self.base_path:
                base_path = self.base_path.resolve()
                try:
                    file_path.relative_to(base_path)
                except ValueError:
                    return file_path, f"Access denied: path outside allowed directory"
            
            # Check extension
            if self.allowed_extensions:
                ext = file_path.suffix.lower()
                if ext not in self.allowed_extensions:
                    return file_path, f"Extension not allowed: {ext}"
            
            # Check existence
            if not file_path.exists():
                return file_path, f"File not found: {path}"
            
            if not file_path.is_file():
                return file_path, f"Not a file: {path}"
            
            # Check size
            size = file_path.stat().st_size
            if size > self.max_file_size:
                return file_path, f"File too large: {size} bytes (max: {self.max_file_size})"
            
            return file_path, None
            
        except Exception as e:
            return Path(path), f"Invalid path: {e}"

    async def run(self, path: str = None, encoding: str = "utf-8", **kwargs) -> str:
        """Read file contents."""
        if path is None:
            path = kwargs.get("input", "")
        
        if not path:
            return "Error: No path provided"
        
        file_path, error = self._validate_path(path)
        if error:
            return f"Error: {error}"
        
        try:
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(
                None, 
                lambda: file_path.read_text(encoding=encoding)
            )
            return content
        except UnicodeDecodeError:
            return f"Error: Cannot decode file with {encoding} encoding"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"


class FileWriteTool(Tool):
    """
    Write contents to a file.
    """
    
    name = "write_file"
    description = "Write content to a file. Creates the file if it doesn't exist."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to write"
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file"
            },
            "append": {
                "type": "boolean",
                "description": "Append to file instead of overwriting (default: false)"
            }
        },
        "required": ["path", "content"]
    }
    output_schema = {"type": "string"}

    def __init__(
        self,
        max_content_size: int = 1_000_000,  # 1MB
        allowed_extensions: Optional[list] = None,
        base_path: Optional[str] = None,
        create_dirs: bool = True,
    ):
        """
        Initialize file write tool.
        
        Args:
            max_content_size: Maximum content size in bytes
            allowed_extensions: List of allowed file extensions (None = all)
            base_path: Base path to restrict file access
            create_dirs: Whether to create parent directories
        """
        self.max_content_size = max_content_size
        self.allowed_extensions = allowed_extensions
        self.base_path = Path(base_path) if base_path else None
        self.create_dirs = create_dirs

    def _validate_path(self, path: str) -> tuple[Path, Optional[str]]:
        """Validate and resolve the file path."""
        try:
            file_path = Path(path).resolve()
            
            # Check base path restriction
            if self.base_path:
                base_path = self.base_path.resolve()
                try:
                    file_path.relative_to(base_path)
                except ValueError:
                    return file_path, f"Access denied: path outside allowed directory"
            
            # Check extension
            if self.allowed_extensions:
                ext = file_path.suffix.lower()
                if ext not in self.allowed_extensions:
                    return file_path, f"Extension not allowed: {ext}"
            
            return file_path, None
            
        except Exception as e:
            return Path(path), f"Invalid path: {e}"

    async def run(
        self, 
        path: str = None, 
        content: str = None, 
        append: bool = False,
        **kwargs
    ) -> str:
        """Write content to file."""
        if path is None:
            path = kwargs.get("input", "")
        if content is None:
            content = kwargs.get("text", "")
        
        if not path:
            return "Error: No path provided"
        if content is None:
            return "Error: No content provided"
        
        # Check content size
        if len(content) > self.max_content_size:
            return f"Error: Content too large ({len(content)} bytes, max: {self.max_content_size})"
        
        file_path, error = self._validate_path(path)
        if error:
            return f"Error: {error}"
        
        try:
            loop = asyncio.get_event_loop()
            
            def write_file():
                if self.create_dirs:
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                
                mode = "a" if append else "w"
                with open(file_path, mode, encoding="utf-8") as f:
                    f.write(content)
                return file_path.stat().st_size
            
            size = await loop.run_in_executor(None, write_file)
            action = "Appended to" if append else "Wrote"
            return f"{action} {path} ({size} bytes)"
            
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"
