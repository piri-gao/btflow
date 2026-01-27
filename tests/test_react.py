"""
Tests for btflow.patterns.react - ReAct Agent Pattern
"""
import asyncio
import unittest
import operator
from typing import Annotated, List, Optional
from pydantic import BaseModel, Field
from py_trees.common import Status
from py_trees.composites import Sequence
from py_trees.behaviour import Behaviour

from btflow.core.behaviour import AsyncBehaviour
from btflow.core.composites import LoopUntilSuccess
from btflow.core.state import StateManager
from btflow.core.runtime import ReactiveRunner
from btflow.patterns.react import ReActState
from btflow.nodes.agents.react import ToolExecutor, IsFinalAnswer
from btflow.tools import Tool, ToolRegistry
from btflow.messages import human, ai


class MockCalculatorTool(Tool):
    """Mock calculator tool for testing"""
    name = "calculator"
    description = "Perform calculations"
    
    def run(self, input: str) -> str:
        try:
            return str(eval(input))
        except Exception as e:
            return f"Error: {e}"


class AsyncEchoTool(Tool):
    """Async tool for testing"""
    name = "echo_async"
    description = "Echo input async"

    async def run(self, input: str) -> str:
        await asyncio.sleep(0.01)
        return f"echo:{input}"


class MockLLMNode(AsyncBehaviour):
    """Mock LLM node that returns predefined responses"""
    def __init__(self, name: str, responses: List[str]):
        super().__init__(name)
        self.responses = responses
        self.call_count = 0
    
    async def update_async(self) -> Status:
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            state = self.state_manager.get()
            self.state_manager.update({
                "messages": [ai(response)],
                "round": state.round + 1
            })
            return Status.SUCCESS
        return Status.FAILURE


class TestIsFinalAnswer(unittest.TestCase):
    """IsFinalAnswer 节点测试"""
    
    def setUp(self):
        self.state_manager = StateManager(schema=ReActState)
        self.state_manager.initialize({})
        self.check = IsFinalAnswer("check", max_rounds=10)
        self.check.state_manager = self.state_manager
    
    def test_no_messages_returns_failure(self):
        """无消息时返回 FAILURE"""
        self.check.setup()
        result = self.check.update()
        self.assertEqual(result, Status.FAILURE)
    
    def test_no_final_answer_returns_failure(self):
        """没有 Final Answer 返回 FAILURE"""
        self.state_manager.update({
            "messages": [ai("Thought: thinking...\nAction: calculator\nInput: 2+2")]
        })
        self.check.setup()
        result = self.check.update()
        self.assertEqual(result, Status.FAILURE)
    
    def test_with_final_answer_returns_success(self):
        """有 Final Answer 返回 SUCCESS"""
        self.state_manager.update({
            "messages": [ai("Thought: done.\nFinal Answer: 42")]
        })
        self.check.setup()
        result = self.check.update()
        self.assertEqual(result, Status.SUCCESS)
        self.assertEqual(self.state_manager.get().final_answer, "42")
    
    def test_max_rounds_exceeded(self):
        """超过最大轮数返回 SUCCESS（强制停止）"""
        self.state_manager.update({
            "messages": [ai("Thought: thinking...")],
            "round": 10  # max_rounds = 10
        })
        self.check.setup()
        result = self.check.update()
        self.assertEqual(result, Status.SUCCESS)
        self.assertEqual(self.state_manager.get().final_answer, "[MAX_ROUNDS_EXCEEDED]")


class TestToolExecutor(unittest.IsolatedAsyncioTestCase):
    """ToolExecutor 节点测试"""
    
    def setUp(self):
        self.state_manager = StateManager(schema=ReActState)
        self.state_manager.initialize({})
        self.executor = ToolExecutor("executor", tools=[MockCalculatorTool()])
        self.executor.state_manager = self.state_manager
    
    async def test_no_action_skips(self):
        """无 Action 时跳过执行"""
        self.state_manager.update({
            "messages": [ai("Thought: thinking...")]
        })
        self.executor.setup()
        self.executor.initialise()
        result = await self.executor.update_async()
        self.assertEqual(result, Status.SUCCESS)
        # 消息数量不变
        self.assertEqual(len(self.state_manager.get().messages), 1)
    
    async def test_executes_action(self):
        """正确执行 Action"""
        self.state_manager.update({
            "messages": [ai("Thought: need to calculate.\nAction: calculator\nInput: 2 + 3")]
        })
        self.executor.setup()
        self.executor.initialise()
        result = await self.executor.update_async()
        self.assertEqual(result, Status.SUCCESS)
        messages = self.state_manager.get().messages
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[-1].role, "tool")
        self.assertEqual(messages[-1].content, "5")

    async def test_executes_json_tool_call(self):
        """JSON ToolCall 应能被解析执行"""
        self.state_manager.update({
            "messages": [ai('Thought: need to calculate.\nToolCall: {"tool":"calculator","arguments":{"input":"2+3"}}')]
        })
        self.executor.setup()
        self.executor.initialise()
        result = await self.executor.update_async()
        self.assertEqual(result, Status.SUCCESS)
        messages = self.state_manager.get().messages
        self.assertEqual(messages[-1].role, "tool")
        self.assertEqual(messages[-1].content, "5")
    
    async def test_unknown_tool(self):
        """未知工具返回错误"""
        self.state_manager.update({
            "messages": [ai("Action: unknown_tool\nInput: test")]
        })
        self.executor.setup()
        self.executor.initialise()
        result = await self.executor.update_async()
        self.assertEqual(result, Status.SUCCESS)
        messages = self.state_manager.get().messages
        self.assertIn("not found", messages[-1].content)

    async def test_registry_registers_function_tool(self):
        """ToolRegistry 的函数工具应能执行并产生 Observation"""
        registry = ToolRegistry()
        registry.register_function(
            name="echo",
            description="Echo input",
            fn=lambda x: f"echo:{x}"
        )

        executor = ToolExecutor("executor", registry=registry)
        executor.state_manager = self.state_manager
        self.state_manager.update({
            "messages": [ai("Action: echo\nInput: hello")]
        })

        executor.setup()
        executor.initialise()
        result = await executor.update_async()
        self.assertEqual(result, Status.SUCCESS)
        messages = self.state_manager.get().messages
        self.assertEqual(messages[-1].role, "tool")
        self.assertEqual(messages[-1].content, "echo:hello")

    async def test_registry_function_tool_kwargs(self):
        """FunctionTool 应支持多参数函数的 kwargs 调用"""
        registry = ToolRegistry()

        def add(a: int, b: int) -> str:
            return str(a + b)

        registry.register_function(
            name="add",
            description="Add two numbers",
            fn=add,
            input_schema={"type": "object"},
        )

        executor = ToolExecutor("executor", registry=registry)
        executor.state_manager = self.state_manager
        self.state_manager.update({
            "messages": [ai('Action: add\nInput: {"a": 1, "b": 2}')]
        })

        executor.setup()
        executor.initialise()
        result = await executor.update_async()
        self.assertEqual(result, Status.SUCCESS)
        messages = self.state_manager.get().messages
        self.assertEqual(messages[-1].content, "3")

    async def test_async_tool_executes(self):
        """Async 工具应被正确 await"""
        executor = ToolExecutor("executor", tools=[AsyncEchoTool()])
        executor.state_manager = self.state_manager
        self.state_manager.update({
            "messages": [ai("Action: echo_async\nInput: hi")]
        })

        executor.setup()
        executor.initialise()
        result = await executor.update_async()
        self.assertEqual(result, Status.SUCCESS)
        messages = self.state_manager.get().messages
        self.assertEqual(messages[-1].content, "echo:hi")


class TestReActIntegration(unittest.IsolatedAsyncioTestCase):
    """ReAct 完整流程集成测试"""
    
    async def test_full_react_loop(self):
        """完整 ReAct 循环测试"""
        # Mock LLM 响应
        responses = [
            "Thought: I need to calculate.\nAction: calculator\nInput: 10 + 5",
            "Thought: The result is 15.\nFinal Answer: 15"
        ]
        
        # 构建节点
        llm_node = MockLLMNode("llm", responses)
        tool_executor = ToolExecutor("tools", tools=[MockCalculatorTool()])
        check_node = IsFinalAnswer("check", max_rounds=10)
        
        # 构建树
        loop_body = Sequence("loop", memory=True, children=[
            llm_node,
            tool_executor,
            check_node
        ])
        root = LoopUntilSuccess("agent", max_iterations=10, child=loop_body)
        
        # 状态管理
        state_manager = StateManager(schema=ReActState)
        state_manager.initialize({"messages": [human("Question: What is 10 + 5?")]})
        
        # 运行
        runner = ReactiveRunner(root, state_manager)
        await runner.run(max_ticks=20)
        
        # 验证
        state = state_manager.get()
        self.assertEqual(state.final_answer, "15")
        self.assertEqual(state.round, 2)
        self.assertEqual(len(state.messages), 4)  # Question + Action + Observation + Final


if __name__ == "__main__":
    unittest.main()
