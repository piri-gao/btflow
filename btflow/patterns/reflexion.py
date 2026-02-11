"""
BTflow Patterns: Reflexion Agent Implementation

Reflexion 是一种 LLM Agent 模式，通过自我反思迭代改进输出质量。

Tree Structure (使用 btflow.LoopUntilSuccess):
    Root (LoopUntilSuccess)
    └── Sequence (memory=True)
        ├── AgentLLMNode    → 生成/改进答案（Answer/Score/Reflection）
        ├── [ToolExecutor]  → (可选) 执行工具调用
        ├── ParserNode      → 解析 Answer/Score/Reflection
        └── ConditionNode   → 检查分数是否达标
"""
import operator
from typing import Annotated, List, Dict, Any, Optional, Type

from pydantic import BaseModel, Field
from py_trees.composites import Sequence

from btflow.core.composites import LoopUntilSuccess
from btflow.core.state import StateManager, TurnField
from btflow.core.agent import BTAgent
from btflow.nodes import AgentLLMNode, ToolExecutor, ParserNode, ConditionNode
from btflow.llm import LLMProvider
from btflow.tools import Tool
from btflow.memory import Memory, create_memory_tools


# ============ State Schema ============

from btflow.messages import Message

class ReflexionState(BaseModel):
    """Reflexion Agent 的状态定义"""
    task: str = ""
    messages: Annotated[List[Message], operator.add] = Field(default_factory=list)
    answer: Annotated[Optional[str], TurnField()] = None
    answer_history: Annotated[List[str], operator.add] = Field(default_factory=list)
    score: Annotated[float, TurnField()] = 0.0
    score_history: Annotated[List[float], operator.add] = Field(default_factory=list)
    reflection: Annotated[Optional[str], TurnField()] = None
    reflection_history: Annotated[List[str], operator.add] = Field(default_factory=list)
    rounds: Annotated[int, TurnField()] = 0
    is_complete: Annotated[bool, TurnField()] = False
    final_answer: Annotated[Optional[str], TurnField()] = None
    actions: Annotated[List[Dict[str, Any]], TurnField()] = Field(default_factory=list)
    tools_desc: str = ""
    tools_schema: List[Dict[str, Any]] = Field(default_factory=list)
    streaming_output: Annotated[str, TurnField()] = ""


# ============ Reflexion Agent Factory ============

REFLEXION_PROMPT = """You are a helpful assistant that iteratively improves answers.

You will receive the user's task and may also see your previous responses in the conversation history.
Each previous response uses this exact format:

Answer: ...
Score: ...
Reflection: ...

On each turn, produce a new response in the EXACT format below. If there is a previous answer,
improve it using the reflection feedback.

Answer: [Your complete answer here]

Score: [A number from 0 to 10, be honest and critical. Use only a number, e.g. 8.5]

Reflection: [If score < 8, explain what could be improved. If score >= 8, write "The answer is satisfactory."]

If Score >= 8, append one extra line:
Final Answer: [Repeat the Answer exactly]

IMPORTANT:
- Use EXACT labels: Answer, Score, Reflection, Final Answer
- Do NOT use other labels like "评分" or "最终答案"
- Do NOT wrap the response in code blocks
- If you need to use tools, output:
  ToolCall: {"tool": "<tool_name>", "arguments": {...}}

Scoring guidelines:
- 0-3: Incorrect or very incomplete
- 4-5: Partially correct but major issues
- 6-7: Mostly correct but could be improved
- 8-9: Good answer with minor issues
- 10: Perfect answer

Be critical and honest in your self-evaluation. Don't give yourself a high score unless the answer is truly excellent."""


class ReflexionAgent:
    """
    Reflexion Agent 工厂类。
    """

    @staticmethod
    def create(
        provider: Optional[LLMProvider] = None,
        tools: Optional[List[Tool]] = None,
        model: str = "gemini-2.5-flash",
        memory: Optional[Memory] = None,
        memory_top_k: int = 5,
        threshold: float = 8.0,
        max_rounds: int = 10,
        state_schema: Type[BaseModel] = ReflexionState,
        structured_tool_calls: bool = True,
        strict_tool_calls: bool = False,
        stream: bool = False,
        streaming_output_key: str = "streaming_output",
        auto_memory_tools: bool = True,
        system_prompt: Optional[str] = None,
    ) -> BTAgent:
        """使用指定 Provider 创建 Reflexion Agent。"""
        tools = tools or []
        provider = provider or LLMProvider.default()

        if memory is not None and auto_memory_tools:
            memory_tools = memory.as_tools() if hasattr(memory, "as_tools") else create_memory_tools(memory)
            existing = {t.name.lower() for t in tools}
            for tool in memory_tools:
                if tool.name.lower() not in existing:
                    tools.append(tool)
                    existing.add(tool.name.lower())

        # Build effective system prompt
        base_prompt = REFLEXION_PROMPT
        if system_prompt:
            base_prompt = f"{system_prompt}\n\n{base_prompt}"

        llm_node = AgentLLMNode(
            name="AgentLLM",
            model=model,
            provider=provider,
            system_prompt=base_prompt,
            memory=memory,
            memory_top_k=memory_top_k,
            structured_tool_calls=structured_tool_calls if tools else False,
            strict_tool_calls=strict_tool_calls,
            stream=stream,
            streaming_output_key=streaming_output_key,
        )

        # Build loop: AgentLLM → [ToolExecutor] → Parser → Condition
        children = [llm_node]

        if tools:
            tool_executor = ToolExecutor(name="ToolExecutor", tools=tools)
            children.append(tool_executor)

        children.extend([
            ParserNode(name="Parser", preset="score"),
            ParserNode(name="ParseFinalAnswer", preset="final_answer"),
            ConditionNode(name="IsGoodEnough", preset="score_gte", threshold=threshold)
        ])

        loop_body = Sequence(name="ReflexionLoop", memory=True, children=children)
        root = LoopUntilSuccess(name="ReflexionAgent", max_iterations=max_rounds, child=loop_body)

        state_manager = StateManager(schema=state_schema)
        state_manager.initialize({})

        return BTAgent(root, state_manager)
