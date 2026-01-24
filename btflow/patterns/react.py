"""
BTflow Patterns: ReAct Agent Implementation.

ReAct (Reasoning + Acting) 是一种 LLM Agent 模式，交替进行推理和工具调用。

Tree Structure (使用 btflow.LoopUntilSuccess):
    Root (LoopUntilSuccess)
    └── Sequence (memory=True)
        ├── ReActLLMNode       → 调用 LLM，输出 Thought/Action/Final Answer
        ├── ToolExecutor       → 检测并执行 Action（无则跳过）
        └── IsFinalAnswer      → 条件：有 Final Answer → SUCCESS，否则 FAILURE
"""
import operator
from typing import Annotated, List, Dict, Any, Optional, Type

from pydantic import BaseModel, Field
from py_trees.composites import Sequence

from btflow.core.composites import LoopUntilSuccess
from btflow.core.state import StateManager
from btflow.core.agent import BTAgent
from btflow.nodes.agents.react import ReActLLMNode, ToolExecutor, IsFinalAnswer
from btflow.llm import LLMProvider, GeminiProvider, AutoProviderFactory
from btflow.tools import Tool
from btflow.memory import BaseMemory


# ============ State Schema ============

from btflow.messages import Message

class ReActState(BaseModel):
    """ReAct Agent 的状态定义"""
    messages: Annotated[List[Message], operator.add] = Field(default_factory=list)
    final_answer: Optional[str] = None
    round: int = 0
    tools_desc: str = ""
    tools_schema: List[Dict[str, Any]] = Field(default_factory=list)


# ============ ReAct Agent Factory ============

class ReActAgent:
    """
    ReAct Agent 工厂类。

    Example:
        from btflow.patterns import ReActAgent
        from btflow.tools import Tool

        class Calculator(Tool):
            name = "calculator"
            description = "Perform calculations"
            def run(self, input: str) -> str:
                return str(eval(input))

        agent = ReActAgent.create(
            provider=GeminiProvider(),
            tools=[Calculator()],
            max_rounds=10
        )

        from btflow.messages import human
        result = await agent.run({"messages": [human("Question: What is 2+2?")]})
        print(result.final_answer)
    """

    @staticmethod
    def create(
        provider: Optional[LLMProvider] = None,
        tools: Optional[List[Tool]] = None,
        model: str = "gemini-2.5-flash",
        memory: Optional[BaseMemory] = None,
        memory_top_k: int = 5,
        max_rounds: int = 10,
        state_schema: Type[BaseModel] = ReActState
    ) -> BTAgent:
        """使用指定 Provider 创建 ReAct Agent。"""
        tools = tools or []
        provider = provider or AutoProviderFactory().select()

        tool_executor = ToolExecutor(name="ToolExecutor", tools=tools)
        tools_desc = tool_executor.get_tools_description()

        llm_node = ReActLLMNode(
            name="ReActLLM",
            model=model,
            provider=provider,
            tools_description=tools_desc,
            memory=memory,
            memory_top_k=memory_top_k,
        )

        loop_body = Sequence(name="ReActLoop", memory=True, children=[
            llm_node,
            tool_executor,
            IsFinalAnswer(name="CheckAnswer", max_rounds=max_rounds)
        ])

        root = LoopUntilSuccess(name="ReActAgent", max_iterations=max_rounds, child=loop_body)

        state_manager = StateManager(schema=state_schema)
        state_manager.initialize({})

        return BTAgent(root, state_manager)
