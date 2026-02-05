import asyncio
import unittest
from pydantic import BaseModel
from btflow import StateManager, node, tool, Status, Sequence, ReactiveRunner

class DummyState(BaseModel):
    value: int = 0
    input: str = ""
    output: str = ""

class TestUnifiedDecorators(unittest.IsolatedAsyncioTestCase):
    
    def setUp(self):
        self.sm = StateManager(DummyState)
        self.sm.initialize()

    def test_node_decorator_variants(self):
        """测试 @node 和 @node() 变体"""
        @node
        def simple_node(state):
            return {"value": 1}
        
        @node(name="CustomNode", description="Desc")
        def named_node(state):
            return {"value": 2}
            
        # 实例化
        n1 = simple_node("n1", state_manager=self.sm)
        n2 = named_node(state_manager=self.sm) # 使用装饰器中的名字
        
        self.assertEqual(n1.name, "n1")
        self.assertEqual(n1.description, "")
        self.assertEqual(n2.name, "CustomNode")
        self.assertEqual(n2.description, "Desc")

    def test_node_docstring_extraction(self):
        """测试从 docstring 提取描述"""
        @node
        def desc_node(state):
            """Hello World"""
            return None
        
        n = desc_node(state_manager=self.sm)
        self.assertEqual(n.description, "Hello World")

    def test_tool_decorator_variants(self):
        """测试 @tool 和 @tool() 变体"""
        @tool
        def simple_tool(input: str):
            return f"echo:{input}"
        
        @tool(name="CustomTool", description="ToolDesc")
        def named_tool(input: str):
            return "ok"
            
        self.assertEqual(simple_tool.name, "simple_tool")
        self.assertEqual(named_tool.name, "CustomTool")
        self.assertEqual(named_tool.description, "ToolDesc")

    async def test_tool_as_node_fluent_api(self):
        """测试 tool.as_node() 流式接口"""
        @tool
        def calc_tool(input: str):
            return "42"
        
        # 将工具转换为节点
        # 模拟工作流模式：从 state.input 读取，存入 state.output
        t_node = calc_tool.as_node(name="MyToolNode")
        t_node.state_manager = self.sm
        
        self.sm.update({"input": "what is life?"})
        
        res_status = await t_node.update_async()
        self.assertEqual(res_status, Status.SUCCESS)
        self.assertEqual(self.sm.get().output, "42")


if __name__ == "__main__":
    unittest.main()
