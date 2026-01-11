import unittest
import asyncio
from btflow import AsyncBehaviour, StateManager, Status
from pydantic import BaseModel

# 简单的 State
class SimpleState(BaseModel):
    count: int = 0

# 模拟一个会"喊"的节点
class EventNode(AsyncBehaviour):
    async def update_async(self) -> Status:
        # 模拟一点微小的异步延迟
        await asyncio.sleep(0.01)
        return Status.SUCCESS

class TestEventDriven(unittest.IsolatedAsyncioTestCase):
    async def test_callback_mechanism(self):
        """测试核心机制：节点完成是否会触发回调"""
        node = EventNode("TestWorker")
        
        # 1. 创建一个 Future 来捕获回调信号
        wake_signal = asyncio.get_running_loop().create_future()
        
        # 2. 模拟 Runner 的行为：绑定回调
        def _on_wake():
            if not wake_signal.done():
                wake_signal.set_result(True)
                
        node.bind_wake_up(_on_wake)
        
        # 3. 启动节点
        node.initialise()
        
        # 4. 关键验证：等待信号被触发
        try:
            await asyncio.wait_for(wake_signal, timeout=1.0)
            triggered = True
        except asyncio.TimeoutError:
            triggered = False
            
        self.assertTrue(triggered, "❌ 节点完成任务后没有触发唤醒回调！")
        self.assertEqual(node.status, Status.INVALID) # 尚未 update，状态未同步是正常的

    async def test_state_subscription(self):
        """测试核心机制：状态变更是否触发订阅"""
        state = StateManager(SimpleState)
        state.initialize()
        
        trigger_count = 0
        def _on_change():
            nonlocal trigger_count
            trigger_count += 1
            
        # 订阅
        state.subscribe(_on_change)
        
        # 更新 -> 应该触发
        state.update({"count": 1})
        self.assertEqual(trigger_count, 1)
        
        # 再次更新 -> 应该再次触发
        state.update({"count": 2})
        self.assertEqual(trigger_count, 2)

if __name__ == '__main__':
    unittest.main()