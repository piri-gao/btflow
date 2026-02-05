"""
BTflow Patterns: Reflexion Agent Implementation

Reflexion 是一种 LLM Agent 模式，通过自我反思迭代改进输出质量。

Tree Structure (使用 btflow.LoopUntilSuccess):
    Root (LoopUntilSuccess)
    └── Sequence (memory=True)
        ├── AgentLLMNode    → 生成/改进答案（Answer/Score/Reflection）
        ├── ParserNode      → 解析 Answer/Score/Reflection
        └── ConditionNode   → 检查分数是否达标
"""
import operator
from typing import Annotated, List, Optional, Type

from pydantic import BaseModel, Field
from py_trees.composites import Sequence

from btflow.core.composites import LoopUntilSuccess
from btflow.core.state import StateManager
from btflow.core.agent import BTAgent
from btflow.nodes import AgentLLMNode, ParserNode, ConditionNode
from btflow.llm import LLMProvider
from btflow.memory import Memory


# ============ State Schema ============

from btflow.messages import Message

class ReflexionState(BaseModel):
    """Reflexion Agent 的状态定义"""
    task: str = ""
    messages: Annotated[List[Message], operator.add] = Field(default_factory=list) # Audit/History
    answer: Optional[str] = None
    answer_history: Annotated[List[str], operator.add] = Field(default_factory=list)
    score: float = 0.0
    score_history: Annotated[List[float], operator.add] = Field(default_factory=list)
    reflection: Optional[str] = None
    reflection_history: Annotated[List[str], operator.add] = Field(default_factory=list)
    rounds: int = 0
    is_complete: bool = False


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

Score: [A number from 0 to 10, be honest and critical]

Reflection: [If score < 8, explain what could be improved. If score >= 8, write "The answer is satisfactory."]

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
        model: str = "gemini-2.5-flash",
        memory: Optional[Memory] = None,
        memory_top_k: int = 5,
        threshold: float = 8.0,
        max_rounds: int = 10,
        state_schema: Type[BaseModel] = ReflexionState
    ) -> BTAgent:
        """使用指定 Provider 创建 Reflexion Agent。"""
        provider = provider or LLMProvider.default()
        llm_node = AgentLLMNode(
            name="AgentLLM",
            model=model,
            provider=provider,
            system_prompt=REFLEXION_PROMPT,
            memory=memory,
            memory_top_k=memory_top_k,
        )

        loop_body = Sequence(name="ReflexionLoop", memory=True, children=[
            llm_node,
            ParserNode(name="Parser", preset="score"),
            ConditionNode(name="IsGoodEnough", preset="score_gte", threshold=threshold)
        ])

        root = LoopUntilSuccess(name="ReflexionAgent", max_iterations=max_rounds, child=loop_body)

        state_manager = StateManager(schema=state_schema)
        state_manager.initialize({})

        return BTAgent(root, state_manager)
