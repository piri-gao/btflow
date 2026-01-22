"""
BTflow Patterns: Reflexion Agent Implementation (Self-Refine)

Reflexion 是一种 LLM Agent 模式，通过自我反思迭代改进输出质量。

Self-Refine 流程：
    1. 生成初始答案
    2. 评估答案质量 (0-10 分)
    3. 如果分数 >= 阈值，完成
    4. 否则，生成反思和改进建议，循环

Tree Structure (使用 btflow.LoopUntilSuccess):
    Root (LoopUntilSuccess)
    └── Sequence (memory=True)
        ├── SelfRefineNode  → 生成/改进答案 + 自我评估
        └── IsGoodEnough    → 检查分数是否达标
"""
import re
import operator
from typing import Annotated, List, Optional, Type
from pydantic import BaseModel, Field
from py_trees.common import Status
from py_trees.composites import Sequence
from py_trees.behaviour import Behaviour

from btflow.core.composites import LoopUntilSuccess
from btflow.core.behaviour import AsyncBehaviour
from btflow.core.state import StateManager
from btflow.core.agent import BTAgent
from btflow.core.logging import logger


# ============ State Schema ============

class ReflexionState(BaseModel):
    """Reflexion Agent 的状态定义"""
    # 用户问题/任务
    task: str = ""
    # 当前答案
    answer: Optional[str] = None
    # 答案历史 (用于追踪改进过程)
    answer_history: Annotated[List[str], operator.add] = Field(default_factory=list)
    # 当前分数 (0-10)
    score: float = 0.0
    # 分数历史
    score_history: Annotated[List[float], operator.add] = Field(default_factory=list)
    # 反思/改进建议
    reflection: Optional[str] = None
    # 反思历史
    reflection_history: Annotated[List[str], operator.add] = Field(default_factory=list)
    # 当前轮数
    round: int = 0
    # 是否完成
    is_complete: bool = False


# ============ Reflexion Nodes ============

class SelfRefineGeminiNode(AsyncBehaviour):
    """
    Self-Refine 节点：生成答案 + 自我评估。
    
    第一轮：生成初始答案并评分
    后续轮：基于反思改进答案并重新评分
    
    输出格式：
        Answer: [答案内容]
        Score: [0-10 的分数]
        Reflection: [如果分数不够高，给出改进建议]
    """
    
    def __init__(
        self,
        name: str = "SelfRefine",
        model: str = "gemini-2.5-flash",
        system_prompt: Optional[str] = None
    ):
        super().__init__(name)
        self.model = model
        self.system_prompt = system_prompt or self._get_default_prompt()
        
        import os
        from google import genai
        
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("⚠️ [{}] GOOGLE_API_KEY not found!", self.name)
        
        self.client = genai.Client(api_key=api_key)
    
    def _get_default_prompt(self) -> str:
        return """You are a helpful assistant that generates high-quality answers and evaluates your own work.

For each task, you must:
1. Generate or improve an answer
2. Critically evaluate your answer and give it a score from 0-10
3. If the score is below 8, provide specific suggestions for improvement

You MUST use this EXACT format:

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
    
    async def update_async(self) -> Status:
        """生成/改进答案并自我评估"""
        import asyncio
        from google.genai import types
        
        try:
            state = self.state_manager.get()
            
            # 构建 prompt
            if state.round == 0:
                # 第一轮：生成初始答案
                prompt = f"Task: {state.task}\n\nGenerate your best answer, evaluate it, and provide your score and reflection."
            else:
                # 后续轮：基于反思改进
                prompt = f"""Task: {state.task}

Previous Answer: {state.answer}

Previous Score: {state.score}

Feedback to address: {state.reflection}

Please improve your answer based on the feedback, then re-evaluate and provide your new score and reflection."""
            
            logger.debug("🤖 [{}] Round {} - 调用 Gemini...", self.name, state.round + 1)
            
            response = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=self.system_prompt,
                        temperature=0.7
                    )
                ),
                timeout=60.0
            )
            
            content = response.text.strip()
            
            if not content:
                logger.warning("⚠️ [{}] LLM 返回空响应", self.name)
                return Status.FAILURE
            
            # 解析响应
            answer, score, reflection = self._parse_response(content)
            
            if answer is None:
                logger.warning("⚠️ [{}] 无法解析 LLM 响应", self.name)
                return Status.FAILURE
            
            # 更新状态
            self.state_manager.update({
                "answer": answer,
                "answer_history": [answer],
                "score": score,
                "score_history": [score],
                "reflection": reflection,
                "reflection_history": [reflection] if reflection else [],
                "round": state.round + 1
            })
            
            logger.info("💭 [{}] Round {} - Score: {:.1f}", self.name, state.round + 1, score)
            if reflection:
                logger.info("   Reflection: {}", reflection)
            logger.debug("   Answer: {}...", answer[:100] if len(answer) > 100 else answer)
            
            return Status.SUCCESS
            
        except asyncio.TimeoutError:
            logger.warning("⏰ [{}] 请求超时", self.name)
            return Status.FAILURE
        except Exception as e:
            logger.warning("⚠️ [{}] Gemini 调用失败 (将自动重试): {}", self.name, e)
            return Status.FAILURE
    
    def _parse_response(self, content: str) -> tuple:
        """解析 LLM 响应，提取 answer, score, reflection"""
        answer = None
        score = 0.0
        reflection = None
        
        # 提取 Answer
        answer_match = re.search(r"Answer:\s*(.+?)(?=\n\s*Score:|$)", content, re.DOTALL | re.IGNORECASE)
        if answer_match:
            answer = answer_match.group(1).strip()
        
        # 提取 Score
        score_match = re.search(r"Score:\s*(\d+(?:\.\d+)?)", content, re.IGNORECASE)
        if score_match:
            score = float(score_match.group(1))
            score = max(0, min(10, score))  # 限制在 0-10
        
        # 提取 Reflection
        reflection_match = re.search(r"Reflection:\s*(.+?)$", content, re.DOTALL | re.IGNORECASE)
        if reflection_match:
            reflection = reflection_match.group(1).strip()
        
        return answer, score, reflection


class IsGoodEnough(Behaviour):
    """
    条件节点：检查答案质量是否达标。
    
    - 分数 >= 阈值 → SUCCESS（循环结束）
    - 分数 < 阈值 → FAILURE（继续改进）
    """
    
    def __init__(
        self, 
        name: str = "IsGoodEnough", 
        threshold: float = 8.0,
        max_rounds: int = 5
    ):
        super().__init__(name)
        self.threshold = threshold
        self.max_rounds = max_rounds
        self.state_manager: Optional[StateManager] = None
    
    def update(self) -> Status:
        """检查分数是否达标"""
        if self.state_manager is None:
            logger.error("❌ [{}] state_manager 未注入", self.name)
            return Status.FAILURE
        
        state = self.state_manager.get()
        
        # 检查是否超过最大轮数
        if state.round >= self.max_rounds:
            logger.warning("⚠️ [{}] 达到最大轮数 ({}), 使用当前最佳答案", 
                         self.name, self.max_rounds)
            self.state_manager.update({"is_complete": True})
            return Status.SUCCESS
        
        # 检查分数
        if state.score >= self.threshold:
            logger.info("✅ [{}] 分数 {:.1f} >= {:.1f}, 答案达标!", 
                       self.name, state.score, self.threshold)
            self.state_manager.update({"is_complete": True})
            return Status.SUCCESS
        
        logger.debug("🔄 [{}] 分数 {:.1f} < {:.1f}, 继续改进 (Round {}/{})", 
                    self.name, state.score, self.threshold, state.round, self.max_rounds)
        
        # 触发 tick_signal
        self.state_manager.update({})
        return Status.FAILURE


# ============ Reflexion Agent Factory ============

class ReflexionAgent:
    """
    Reflexion Agent 工厂类 (Self-Refine 版本)。
    
    Example:
        from btflow.patterns import ReflexionAgent
        
        agent = ReflexionAgent.create_with_gemini(
            threshold=8.0,  # 分数阈值
            max_rounds=5    # 最大改进轮数
        )
        
        result = await agent.run({
            "task": "Write a haiku about programming"
        })
        
        state = agent.state_manager.get()
        print(f"Final Answer: {state.answer}")
        print(f"Final Score: {state.score}")
        print(f"Rounds: {state.round}")
    """
    
    @staticmethod
    def create_with_gemini(
        model: str = "gemini-2.5-flash",
        threshold: float = 8.0,
        max_rounds: int = 5,
        state_schema: Type[BaseModel] = ReflexionState
    ) -> BTAgent:
        """
        使用 Gemini 创建 Self-Refine Agent。
        
        Args:
            model: Gemini 模型名称
            threshold: 分数阈值 (0-10)，达到则停止
            max_rounds: 最大改进轮数
            state_schema: 状态 Schema（默认 ReflexionState）
        
        Returns:
            配置好的 BTAgent 实例
        """
        # 创建节点
        refine_node = SelfRefineGeminiNode(
            name="SelfRefine",
            model=model
        )
        
        check_node = IsGoodEnough(
            name="CheckQuality",
            threshold=threshold,
            max_rounds=max_rounds
        )
        
        # 构建循环体
        loop_body = Sequence(name="RefineLoop", memory=True, children=[
            refine_node,
            check_node
        ])
        
        # 使用 LoopUntilSuccess 控制循环
        root = LoopUntilSuccess(
            name="ReflexionAgent",
            max_iterations=max_rounds,
            child=loop_body
        )
        
        # 创建状态管理器
        state_manager = StateManager(schema=state_schema)
        state_manager.initialize({})
        
        # 创建 Agent
        return BTAgent(root, state_manager)
