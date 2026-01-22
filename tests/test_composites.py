"""
Tests for btflow.core.composites - LoopUntilSuccess
"""
import asyncio
import unittest
from py_trees.common import Status
from py_trees.composites import Sequence
from py_trees.behaviour import Behaviour

from btflow.core.composites import LoopUntilSuccess
from btflow.core.state import StateManager
from btflow.core.runtime import ReactiveRunner
from pydantic import BaseModel


class SimpleState(BaseModel):
    counter: int = 0


class SucceedAfterN(Behaviour):
    """测试用节点：在第 N 次 tick 后返回 SUCCESS"""
    def __init__(self, name: str, n: int):
        super().__init__(name)
        self.n = n
        self.tick_count = 0
        self.state_manager = None
    
    def update(self) -> Status:
        self.tick_count += 1
        if self.tick_count >= self.n:
            return Status.SUCCESS
        # 触发 tick_signal 以便 event-driven 模式继续
        if self.state_manager:
            self.state_manager.update({"counter": self.tick_count})
        return Status.FAILURE


class AlwaysSucceed(Behaviour):
    """总是返回 SUCCESS"""
    def update(self) -> Status:
        return Status.SUCCESS


class AlwaysFail(Behaviour):
    """总是返回 FAILURE"""
    def __init__(self, name: str):
        super().__init__(name)
        self.state_manager = None
    
    def update(self) -> Status:
        if self.state_manager:
            self.state_manager.update({})
        return Status.FAILURE


class TestLoopUntilSuccess(unittest.TestCase):
    """LoopUntilSuccess 单元测试"""
    
    def test_success_on_first_try(self):
        """子节点第一次就成功"""
        child = AlwaysSucceed("child")
        loop = LoopUntilSuccess("loop", child=child, max_iterations=10)
        
        loop.setup()
        loop.tick_once()
        
        self.assertEqual(loop.status, Status.SUCCESS)
        self.assertEqual(loop.iteration_count, 0)
    
    def test_success_after_n_failures(self):
        """子节点失败 N 次后成功"""
        child = SucceedAfterN("child", n=3)
        loop = LoopUntilSuccess("loop", child=child, max_iterations=10)
        
        loop.setup()
        
        # 第 1 次 tick: 子节点失败
        loop.tick_once()
        self.assertEqual(loop.status, Status.RUNNING)
        self.assertEqual(loop.iteration_count, 1)
        
        # 第 2 次 tick: 子节点失败
        loop.tick_once()
        self.assertEqual(loop.status, Status.RUNNING)
        self.assertEqual(loop.iteration_count, 2)
        
        # 第 3 次 tick: 子节点成功
        loop.tick_once()
        self.assertEqual(loop.status, Status.SUCCESS)
    
    def test_max_iterations_exceeded(self):
        """超过最大迭代次数返回 FAILURE"""
        child = AlwaysFail("child")
        loop = LoopUntilSuccess("loop", child=child, max_iterations=3)
        
        loop.setup()
        
        loop.tick_once()  # iteration 1
        self.assertEqual(loop.status, Status.RUNNING)
        
        loop.tick_once()  # iteration 2
        self.assertEqual(loop.status, Status.RUNNING)
        
        loop.tick_once()  # iteration 3 = max, should fail
        self.assertEqual(loop.status, Status.FAILURE)


class TestLoopUntilSuccessEventDriven(unittest.IsolatedAsyncioTestCase):
    """LoopUntilSuccess 在 event-driven 模式下的测试"""
    
    async def test_loop_with_runner(self):
        """与 ReactiveRunner 配合工作"""
        child = SucceedAfterN("child", n=3)
        loop = LoopUntilSuccess("loop", child=child, max_iterations=10)
        
        state_manager = StateManager(schema=SimpleState)
        state_manager.initialize({})
        
        runner = ReactiveRunner(loop, state_manager)
        
        await runner.run(max_ticks=20)
        
        # 应该成功结束
        self.assertEqual(loop.status, Status.SUCCESS)
        # 子节点应该被 tick 了 3 次
        self.assertEqual(child.tick_count, 3)


if __name__ == "__main__":
    unittest.main()
