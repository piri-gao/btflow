"""
BTflow Patterns: Reflexion Agent Implementation (Self-Refine)

Reflexion 是一种 LLM Agent 模式，通过自我反思迭代改进输出质量。

Tree Structure (使用 btflow.LoopUntilSuccess):
    Root (LoopUntilSuccess)
    └── Sequence (memory=True)
        ├── SelfRefineNode  → 生成/改进答案 + 自我评估
        └── IsGoodEnough    → 检查分数是否达标
"""
import operator
from typing import Annotated, List, Optional, Type

from pydantic import BaseModel, Field
from py_trees.composites import Sequence

from btflow.core.composites import LoopUntilSuccess
from btflow.core.state import StateManager
from btflow.core.agent import BTAgent
from btflow.nodes.agents.reflexion import SelfRefineGeminiNode, IsGoodEnough


# ============ State Schema ============

class ReflexionState(BaseModel):
    """Reflexion Agent 的状态定义"""
    task: str = ""
    answer: Optional[str] = None
    answer_history: Annotated[List[str], operator.add] = Field(default_factory=list)
    score: float = 0.0
    score_history: Annotated[List[float], operator.add] = Field(default_factory=list)
    reflection: Optional[str] = None
    reflection_history: Annotated[List[str], operator.add] = Field(default_factory=list)
    round: int = 0
    is_complete: bool = False


# ============ Reflexion Agent Factory ============

class ReflexionAgent:
    """
    Reflexion Agent 工厂类。
    """

    @staticmethod
    def create_with_gemini(
        model: str = "gemini-2.5-flash",
        threshold: float = 8.0,
        max_rounds: int = 10,
        state_schema: Type[BaseModel] = ReflexionState
    ) -> BTAgent:
        """
        使用 Gemini 创建 Reflexion Agent。
        """
        llm_node = SelfRefineGeminiNode(
            name="SelfRefine",
            model=model
        )

        loop_body = Sequence(name="ReflexionLoop", memory=True, children=[
            llm_node,
            IsGoodEnough(name="IsGoodEnough", threshold=threshold, max_rounds=max_rounds)
        ])

        root = LoopUntilSuccess(name="ReflexionAgent", max_iterations=max_rounds, child=loop_body)

        state_manager = StateManager(schema=state_schema)
        state_manager.initialize({})

        return BTAgent(root, state_manager)
