"""
BTAgent 测试：验证双模驱动核心功能
"""
import unittest
import asyncio
import operator
from typing import Annotated, List, Optional
from pydantic import BaseModel, Field

from btflow import BTAgent, StateManager, ActionField, AsyncBehaviour, ReactiveRunner, Status, Behaviour


# 测试用 State Schema
class AgentTestState(BaseModel):
    observation: dict = Field(default_factory=dict)
    messages: Annotated[List[str], operator.add] = Field(default_factory=list)
    # ActionField 标记的动作字段
    speed: Annotated[float, ActionField()] = 0.0
    fire: Annotated[bool, ActionField()] = False


# 同步动作节点（模拟"肌肉节点"，用于 step 模式测试）
class SyncActionNode(Behaviour):
    """同步节点：立即写入动作并返回 SUCCESS"""
    def __init__(self, name: str):
        super().__init__(name)
        self.state_manager: StateManager = None
    
    def update(self) -> Status:
        obs = self.state_manager.get().observation
        if obs.get("target"):
            self.state_manager.update({"speed": 1.0, "fire": True})
        return Status.SUCCESS


# 异步动作节点（模拟"大脑节点"）
class AsyncActionNode(AsyncBehaviour):
    """异步节点：写入动作后成功（需要多帧）"""
    def __init__(self, name: str):
        super().__init__(name)
        self.state_manager: StateManager = None
    
    async def update_async(self) -> Status:
        obs = self.state_manager.get().observation
        if obs.get("target"):
            self.state_manager.update({"speed": 1.0, "fire": True})
        return Status.SUCCESS


class TestBTAgentStep(unittest.IsolatedAsyncioTestCase):
    """测试 step() 模式"""
    
    def setUp(self):
        self.state = StateManager(AgentTestState)
        self.state.initialize()
        
        # 简单的单节点树（同步节点用于 step 测试）
        self.root = SyncActionNode("Action")
        # Runner is created inside BTAgent now for the default constructor
        # If we need access to runner, we can access agent.runner
        self.agent = BTAgent(self.root, self.state)
        # For testing purposes, we can alias agent.runner if needed
        self.runner = self.agent.runner
    
    async def test_step_returns_actions(self):
        """step() 应返回 ActionField 标记的字段"""
        actions = await self.agent.step({"observation": {"target": True}})
        
        self.assertIn("speed", actions)
        self.assertIn("fire", actions)
        self.assertEqual(actions["speed"], 1.0)
        self.assertEqual(actions["fire"], True)
    
    async def test_step_resets_actions_each_frame(self):
        """step() 应在每帧重置动作，不残留"""
        # 第一帧：有目标，应该开火
        actions1 = await self.agent.step({"observation": {"target": True}})
        self.assertTrue(actions1["fire"])
        
        # 第二帧：无目标，动作应重置
        actions2 = await self.agent.step({"observation": {}})
        self.assertFalse(actions2["fire"])
        self.assertEqual(actions2["speed"], 0.0)
    
    async def test_step_does_not_use_signal(self):
        """step() 不应触发 tick_signal"""
        # 确保 auto_driving 在 step 期间是关闭的
        # 这里通过检查信号未被 set 来验证
        self.runner.tick_signal.clear()
        
        await self.agent.step({})
        
        # 信号不应被 set（因为 auto_driving=False）
        self.assertFalse(self.runner.tick_signal.is_set())


class TestBTAgentReset(unittest.IsolatedAsyncioTestCase):
    """测试 reset() 功能"""
    
    def setUp(self):
        self.state = StateManager(AgentTestState)
        self.state.initialize()
        
        self.root = SyncActionNode("Action")
        # Runner is created inside BTAgent now for the default constructor
        self.agent = BTAgent(self.root, self.state)
        self.runner = self.agent.runner
    
    async def test_reset_clears_agent_state(self):
        """reset() 应重置 agent 状态"""
        # 先执行一帧
        await self.agent.step({})
        self.assertEqual(self.root.status, Status.SUCCESS)
        
        # reset 应清除信号和模式
        self.agent.reset(reset_data=False)
        
        # 验证 agent 状态已重置
        self.assertEqual(self.agent._mode, "idle")
        self.assertFalse(self.runner.auto_driving)
        self.assertFalse(self.runner.tick_signal.is_set())
    
    async def test_reset_data_clears_messages(self):
        """reset(reset_data=True) 应清空黑板"""
        # 添加一些消息
        self.state.update({"messages": ["hello"]})
        self.assertEqual(len(self.state.get().messages), 1)
        
        # reset with data
        self.agent.reset(reset_data=True)
        self.assertEqual(len(self.state.get().messages), 0)
    
    async def test_reset_preserves_data_when_false(self):
        """reset(reset_data=False) 应保留黑板"""
        self.state.update({"messages": ["hello"]})
        
        self.agent.reset(reset_data=False)
        self.assertEqual(len(self.state.get().messages), 1)


class TestActionField(unittest.IsolatedAsyncioTestCase):
    """测试 ActionField 标记功能"""
    
    def test_action_field_detected(self):
        """ActionField 字段应被正确检测"""
        state = StateManager(AgentTestState)
        
        # 应检测到 speed 和 fire
        self.assertIn("speed", state._action_fields)
        self.assertIn("fire", state._action_fields)
        # messages 不是 ActionField
        self.assertNotIn("messages", state._action_fields)
    
    def test_reset_actions(self):
        """reset_actions() 应重置所有 ActionField 字段"""
        state = StateManager(AgentTestState)
        state.initialize()
        
        # 设置动作
        state.update({"speed": 5.0, "fire": True})
        self.assertEqual(state.get().speed, 5.0)
        self.assertTrue(state.get().fire)
        
        # reset
        state.reset_actions()
        self.assertEqual(state.get().speed, 0.0)
        self.assertFalse(state.get().fire)
    
    def test_get_actions(self):
        """get_actions() 应只返回 ActionField 字段"""
        state = StateManager(AgentTestState)
        state.initialize({"speed": 1.0, "fire": True, "observation": {"x": 1}})
        
        actions = state.get_actions()
        
        self.assertEqual(actions["speed"], 1.0)
        self.assertEqual(actions["fire"], True)
        # observation 不应在 actions 中
        self.assertNotIn("observation", actions)
    
    def test_mutable_action_field_reset(self):
        """reset_actions() 应对 List 等可变类型生成新实例，避免脏数据累积"""
        from pydantic import Field
        
        # 定义带有 List ActionField 的 State
        class StateWithList(BaseModel):
            targets: Annotated[List[str], ActionField()] = Field(default_factory=list)
        
        state = StateManager(StateWithList)
        state.initialize()
        
        # 第1帧：重置后修改
        state.reset_actions()
        state.update({"targets": ["Enemy1"]})  # 通过 update 修改
        self.assertEqual(state.get().targets, ["Enemy1"])
        
        # 第2帧：重置应得到全新的空列表
        state.reset_actions()
        self.assertEqual(state.get().targets, [])  # 应为空，不残留


if __name__ == '__main__':
    unittest.main()
