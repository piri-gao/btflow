"""
Python REPL Tool - Execute Python code snippets safely.
"""
import asyncio
import sys
import io
import traceback
from typing import Any, Optional, Dict
from contextlib import redirect_stdout, redirect_stderr

from btflow.tools import Tool


class PythonREPLTool(Tool):
    """
    Execute Python code and return the output.
    
    WARNING: This tool executes arbitrary Python code. Use with caution
    and consider sandboxing in production environments.
    """
    
    name = "python_repl"
    description = "Execute Python code and return the output. Use for calculations, data processing, or any Python operation."
    input_schema = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "The Python code to execute"
            }
        },
        "required": ["code"]
    }
    output_schema = {"type": "string"}

    def __init__(
        self,
        timeout: float = 30.0,
        max_output_length: int = 10000,
        allowed_modules: Optional[list] = None,
        globals_dict: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize Python REPL tool.
        
        Args:
            timeout: Maximum execution time in seconds
            max_output_length: Maximum output string length
            allowed_modules: List of allowed module names (None = all allowed)
            globals_dict: Custom globals dict for code execution
        """
        self.timeout = timeout
        self.max_output_length = max_output_length
        self.allowed_modules = allowed_modules
        self._globals = globals_dict or {"__builtins__": __builtins__}
        self._locals: Dict[str, Any] = {}

    def _execute_code(self, code: str) -> str:
        """Execute code synchronously and capture output."""
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        try:
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                # Try eval first (for single expressions like "2+2")
                try:
                    eval_result = eval(code, self._globals, self._locals)
                    # If eval succeeds and returns something meaningful, use it
                    if eval_result is not None:
                        result = str(eval_result)
                    else:
                        result = stdout_capture.getvalue()
                except SyntaxError:
                    # If eval fails with SyntaxError, use exec for statements
                    exec(code, self._globals, self._locals)
                    result = stdout_capture.getvalue()
                
                stderr_output = stderr_capture.getvalue()
                if stderr_output:
                    result = result + "\n[stderr]\n" + stderr_output if result else stderr_output
                    
                return result.strip() if result else "(No output)"
                
        except Exception as e:
            tb = traceback.format_exc()
            return f"Error: {type(e).__name__}: {e}\n{tb}"

    async def run(self, code: str = None, **kwargs) -> str:
        """Execute Python code asynchronously with timeout."""
        if code is None:
            code = kwargs.get("input", "")
        
        if not code.strip():
            return "Error: No code provided"
        
        try:
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self._execute_code, code),
                timeout=self.timeout
            )
            
            # Truncate if too long
            if len(result) > self.max_output_length:
                result = result[:self.max_output_length] + f"\n... (truncated, {len(result)} chars total)"
            
            return result
            
        except asyncio.TimeoutError:
            return f"Error: Code execution timed out after {self.timeout}s"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"
