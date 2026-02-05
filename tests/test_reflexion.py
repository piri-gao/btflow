"""
Tests for btflow.patterns.reflexion - Reflexion Agent Pattern
"""
import asyncio
import unittest
from typing import List
from py_trees.common import Status
from py_trees.composites import Sequence

from btflow.core.behaviour import AsyncBehaviour
from btflow.core.composites import LoopUntilSuccess
from btflow.core.state import StateManager
from btflow.core.runtime import ReactiveRunner
from btflow.patterns.reflexion import ReflexionState
from btflow.nodes import ConditionNode


class MockReflexionNode(AsyncBehaviour):
    """Mock Reflexion node for testing"""
    def __init__(self, name: str, scores: List[float]):
        super().__init__(name)
        self.scores = scores
        self.call_count = 0
    
    async def update_async(self) -> Status:
        if self.call_count < len(self.scores):
            score = self.scores[self.call_count]
            self.call_count += 1
            state = self.state_manager.get()
            self.state_manager.update({
                "answer": f"Answer version {self.call_count}",
                "answer_history": [f"Answer version {self.call_count}"],
                "score": score,
                "score_history": [score],
                "reflection": f"Reflection {self.call_count}" if score < 8.0 else "Good enough",
                "rounds": state.rounds + 1
            })
            return Status.SUCCESS
        return Status.FAILURE


class TestConditionScore(unittest.TestCase):
    """ConditionNode score_gte 测试"""
    
    def setUp(self):
        self.state_manager = StateManager(schema=ReflexionState)
        self.state_manager.initialize({})
        self.check = ConditionNode("check", preset="score_gte", threshold=8.0, max_rounds=5)
        self.check.state_manager = self.state_manager
    
    def test_low_score_returns_failure(self):
        """低分返回 FAILURE"""
        self.state_manager.update({"score": 5.0, "rounds": 1})
        self.check.setup()
        result = self.check.update()
        self.assertEqual(result, Status.FAILURE)
    
    def test_high_score_returns_success(self):
        """高分返回 SUCCESS"""
        self.state_manager.update({"score": 8.5, "rounds": 1})
        self.check.setup()
        result = self.check.update()
        self.assertEqual(result, Status.SUCCESS)
        self.assertTrue(self.state_manager.get().is_complete)
    
    def test_threshold_exact_returns_success(self):
        """刚好达到阈值返回 SUCCESS"""
        self.state_manager.update({"score": 8.0, "rounds": 1})
        self.check.setup()
        result = self.check.update()
        self.assertEqual(result, Status.SUCCESS)
    
    def test_max_rounds_exceeded(self):
        """达到最大轮数返回 SUCCESS"""
        self.state_manager.update({"score": 5.0, "rounds": 5})  # max_rounds = 5
        max_rounds_check = ConditionNode("max_rounds", preset="max_rounds", max_rounds=5)
        max_rounds_check.state_manager = self.state_manager
        max_rounds_check.setup()
        result = max_rounds_check.update()
        self.assertEqual(result, Status.SUCCESS)


class TestReflexionIntegration(unittest.IsolatedAsyncioTestCase):
    """Reflexion 完整流程集成测试"""
    
    async def test_immediate_success(self):
        """第一轮就达标"""
        refine_node = MockReflexionNode("refine", scores=[9.0])
        check_node = ConditionNode("check", preset="score_gte", threshold=8.0, max_rounds=5)
        
        loop_body = Sequence("loop", memory=True, children=[
            refine_node,
            check_node
        ])
        root = LoopUntilSuccess("agent", max_iterations=5, child=loop_body)
        
        state_manager = StateManager(schema=ReflexionState)
        state_manager.initialize({"task": "Test task"})
        
        runner = ReactiveRunner(root, state_manager)
        await runner.run(max_ticks=20)
        
        state = state_manager.get()
        self.assertEqual(state.score, 9.0)
        self.assertEqual(state.rounds, 1)
        self.assertTrue(state.is_complete)
    
    async def test_iterative_improvement(self):
        """多轮改进达标"""
        # 分数逐渐提高: 5.0 -> 6.5 -> 8.5
        refine_node = MockReflexionNode("refine", scores=[5.0, 6.5, 8.5])
        check_node = ConditionNode("check", preset="score_gte", threshold=8.0, max_rounds=5)
        
        loop_body = Sequence("loop", memory=True, children=[
            refine_node,
            check_node
        ])
        root = LoopUntilSuccess("agent", max_iterations=5, child=loop_body)
        
        state_manager = StateManager(schema=ReflexionState)
        state_manager.initialize({"task": "Test task"})
        
        runner = ReactiveRunner(root, state_manager)
        await runner.run(max_ticks=30)
        
        state = state_manager.get()
        self.assertEqual(state.score, 8.5)
        self.assertEqual(state.rounds, 3)
        self.assertEqual(len(state.score_history), 3)
    
    async def test_max_rounds_termination(self):
        """达到最大轮数后终止"""
        # 分数始终不够高
        refine_node = MockReflexionNode("refine", scores=[4.0, 5.0, 6.0, 6.5, 7.0])
        check_node = ConditionNode("check", preset="score_gte", threshold=8.0, max_rounds=3)
        
        loop_body = Sequence("loop", memory=True, children=[
            refine_node,
            check_node
        ])
        root = LoopUntilSuccess("agent", max_iterations=3, child=loop_body)
        
        state_manager = StateManager(schema=ReflexionState)
        state_manager.initialize({"task": "Test task"})
        
        runner = ReactiveRunner(root, state_manager)
        await runner.run(max_ticks=30)
        
        state = state_manager.get()
        # 第 3 轮时因为达到 max_rounds 而强制结束
        self.assertEqual(state.rounds, 3)
        self.assertFalse(state.is_complete)


if __name__ == "__main__":
    unittest.main()
