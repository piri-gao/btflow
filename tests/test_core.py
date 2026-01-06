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

    async def test_node_reentry(self):
        """
        � 关键测试：节点重入
        验证节点在 SUCCESS 后可以再次执行
        """
        node = SimpleNode("Reentry")
        
        # 第 1 轮执行
        node.initialise()
        await node.async_task
        status1 = node.update()
        self.assertEqual(status1, Status.SUCCESS)
        self.assertEqual(node.execution_count, 1)
        
        # 模拟 py_trees 调用 terminate
        node.terminate(Status.SUCCESS)
        self.assertIsNone(node.async_task)
        
        # 第 2 轮执行（节点重入）
        node.initialise()
        self.assertIsNotNone(node.async_task, "节点应该能重新创建任务！")
        await node.async_task
        status2 = node.update()
        self.assertEqual(status2, Status.SUCCESS)
        self.assertEqual(node.execution_count, 2)  # 应该执行了 2 次

if __name__ == '__main__':
    unittest.main()