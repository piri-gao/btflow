"""
Tests for btflow.nodes.builtin.parser - ParserNode presets
"""
import unittest
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field
from py_trees.common import Status

from btflow.core.state import StateManager
from btflow.nodes import ParserNode
from btflow.messages import Message, ai


class ParserState(BaseModel):
    messages: List[Message] = Field(default_factory=list)
    final_answer: Optional[str] = None
    answer: Optional[str] = None
    answer_history: List[str] = Field(default_factory=list)
    score: float = 0.0
    score_history: List[float] = Field(default_factory=list)
    reflection: Optional[str] = None
    reflection_history: List[str] = Field(default_factory=list)
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    parsed: Optional[str] = None


class TestParserNode(unittest.TestCase):
    def setUp(self):
        self.state_manager = StateManager(schema=ParserState)
        self.state_manager.initialize({})

    def test_final_answer_preset(self):
        self.state_manager.update({
            "messages": [ai("Thought: done.\nFinal Answer: 42")]
        })
        node = ParserNode("parser", preset="final_answer")
        node.state_manager = self.state_manager
        result = node.update()
        self.assertEqual(result, Status.SUCCESS)
        self.assertEqual(self.state_manager.get().final_answer, "42")

    def test_score_preset(self):
        content = (
            "Answer: The result is 7.\n"
            "Score: 8.5\n"
            "Reflection: The answer is satisfactory."
        )
        self.state_manager.update({
            "messages": [ai(content)]
        })
        node = ParserNode("parser", preset="score")
        node.state_manager = self.state_manager
        result = node.update()
        state = self.state_manager.get()
        self.assertEqual(result, Status.SUCCESS)
        self.assertEqual(state.answer, "The result is 7.")
        self.assertEqual(state.score, 8.5)
        self.assertEqual(state.reflection, "The answer is satisfactory.")
        self.assertEqual(state.answer_history[-1], "The result is 7.")
        self.assertEqual(state.score_history[-1], 8.5)
        self.assertEqual(state.reflection_history[-1], "The answer is satisfactory.")

    def test_action_preset(self):
        content = (
            "Thought: use a tool.\n"
            "ToolCall: {\"tool\": \"calculator\", \"arguments\": {\"input\": \"2+2\"}}"
        )
        self.state_manager.update({
            "messages": [ai(content)]
        })
        node = ParserNode("parser", preset="action")
        node.state_manager = self.state_manager
        result = node.update()
        self.assertEqual(result, Status.SUCCESS)
        actions = self.state_manager.get().actions
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["tool"], "calculator")
        self.assertEqual(actions[0]["arguments"], {"input": "2+2"})

    def test_custom_preset(self):
        self.state_manager.update({
            "messages": [ai("Score: 9.1")]
        })
        node = ParserNode("parser", preset="custom", custom_pattern=r"Score:\s*([0-9.]+)")
        node.state_manager = self.state_manager
        result = node.update()
        self.assertEqual(result, Status.SUCCESS)
        self.assertEqual(self.state_manager.get().parsed, "9.1")


if __name__ == "__main__":
    unittest.main()
