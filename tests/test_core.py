import unittest
import asyncio
from py_trees.common import Status
from btflow.core import AsyncBehaviour

# 定义一个简单的实现类
class SimpleNode(AsyncBehaviour):
    def __init__(self, name):
        super().__init__(name)
        self.execution_count = 0

    async def update_async(self) -> Status:
        self.execution_count += 1
        return Status.SUCCESS

class TestAsyncNode(unittest.IsolatedAsyncioTestCase):
    """
    使用 IsolatedAsyncioTestCase 来测试异步代码
    """
    
    def test_initial_state(self):
        node = SimpleNode("TestNode")
        self.assertEqual(node.status, Status.INVALID)
        self.assertIsNone(node.async_task)

    async def test_normal_lifecycle(self):
        """测试正常的启动流程"""
        node = SimpleNode("Worker")
        
        # 1. 模拟被 Tick (py_trees 会先调 initialise)
        node.initialise()
        
        # 断言：任务已创建
        self.assertIsNotNone(node.async_task)
        self.assertFalse(node.async_task.done())
        
        # 2. 等待任务完成
        await node.async_task
        
        # 3. 模拟 update
        status = node.update()
        self.assertEqual(status, Status.SUCCESS)
        self.assertEqual(node.execution_count, 1)

    async def test_zombie_guard(self):
        """
        🛡️ 关键测试：测试幂等性守卫
        验证当状态已经是 SUCCESS 时，initialise 是否会拦截任务创建
        """
        node = SimpleNode("Zombie")
        
        # 1. 强制设定状态为 SUCCESS (模拟从存档恢复)
        node.status = Status.SUCCESS
        
        # 2. 调用 initialise
        node.initialise()
        
        # 3. 断言：绝不应该创建 Task！
        # 如果这里报错，说明 core.py 里的 if return 没写对
        self.assertIsNone(node.async_task, "僵尸守卫失效！不应该创建任务")
        
        # 4. 断言：update 应该透传状态
        status = node.update()
        self.assertEqual(status, Status.SUCCESS)
        self.assertEqual(node.execution_count, 0) # 根本没跑！

if __name__ == '__main__':
    unittest.main()