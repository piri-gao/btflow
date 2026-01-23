from typing import Any

from btflow.tools.base import Tool


class CalculatorTool(Tool):
    """A simple calculator tool that evaluates math expressions."""
    name = "calculator"
    description = "Performs basic math calculations. Input should be a valid Python math expression like '2+2' or '3*4-5'."
    input_schema = {"type": "string", "description": "Python math expression, e.g. '2+2'"}
    output_schema = {"type": "string", "description": "Result of the expression"}

    def run(self, input: str) -> str:
        try:
            # Allow only math characters
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
    input_schema = {"type": "string", "description": "Search query"}
    output_schema = {"type": "string", "description": "Search results snippet"}

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
    input_schema = {"type": "string", "description": "Topic or person name"}
    output_schema = {"type": "string", "description": "Summary text"}

    def run(self, input: str) -> str:
        return (
            f"Wikipedia summary for '{input}': "
            "This is a mock Wikipedia tool. In production, integrate with real Wikipedia API."
        )
