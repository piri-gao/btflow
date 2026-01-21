"""
BTflow Patterns: Tool abstraction for ReAct and other patterns.
"""
from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """
    Tool base class for agent patterns.
    
    Subclass this and implement the `run` method to create custom tools.
    
    Example:
        class CalculatorTool(Tool):
            name = "calculator"
            description = "Performs basic math calculations. Input: a math expression like '2+2'"
            
            def run(self, input: str) -> str:
                try:
                    return str(eval(input))
                except:
                    return "Error: Invalid expression"
    """
    name: str = "unnamed_tool"
    description: str = "No description provided"
    
    @abstractmethod
    def run(self, input: str) -> str:
        """
        Execute the tool with given input.
        
        Args:
            input: The input string from the LLM's action
            
        Returns:
            Result string to be used as observation
        """
        pass


# ============ Built-in Tools ============

class CalculatorTool(Tool):
    """A simple calculator tool that evaluates math expressions."""
    name = "calculator"
    description = "Performs basic math calculations. Input should be a valid Python math expression like '2+2' or '3*4-5'."
    
    def run(self, input: str) -> str:
        try:
            # 安全地只允许数学表达式
            allowed_chars = set("0123456789+-*/().% ")
            if not all(c in allowed_chars for c in input):
                return f"Error: Only math expressions allowed, got: {input}"
            result = eval(input)
            return str(result)
        except Exception as e:
            return f"Error: {e}"


class SearchTool(Tool):
    """A mock search tool for demonstration purposes."""
    name = "search"
    description = "Search the web for information. Input should be a search query."
    
    # 预设的模拟搜索结果
    _mock_results = {
        "capital of france": "Paris is the capital of France.",
        "population of china": "China has a population of approximately 1.4 billion people.",
        "einstein birthday": "Albert Einstein was born on March 14, 1879.",
        "python creator": "Python was created by Guido van Rossum and first released in 1991.",
    }
    
    def run(self, input: str) -> str:
        query = input.lower().strip()
        for key, value in self._mock_results.items():
            if key in query:
                return value
        return f"Search results for '{input}': No specific results found. This is a mock search tool."


class WikipediaTool(Tool):
    """A mock Wikipedia lookup tool."""
    name = "wikipedia"
    description = "Look up information on Wikipedia. Input should be a topic or person name."
    
    def run(self, input: str) -> str:
        # 简化的模拟实现
        return f"Wikipedia summary for '{input}': This is a mock Wikipedia tool. In production, integrate with real Wikipedia API."
