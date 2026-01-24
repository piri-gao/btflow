import asyncio
import re
from typing import Optional, List

from py_trees.common import Status
from py_trees.behaviour import Behaviour

from btflow.core.behaviour import AsyncBehaviour
from btflow.core.logging import logger
from btflow.llm import LLMProvider, GeminiProvider


from btflow.messages import Message, human, ai
from btflow.context.builder import ContextBuilder

class SelfRefineLLMNode(AsyncBehaviour):
    """
    Self-Refine 节点：生成答案 + 自我评估。
    """

    def __init__(
        self,
        name: str = "SelfRefine",
        model: str = "gemini-2.5-flash",
        provider: Optional[LLMProvider] = None,
        system_prompt: Optional[str] = None
    ):
        super().__init__(name)
        self.model = model
        self.system_prompt = system_prompt or self._get_default_prompt()
        self.provider = provider or GeminiProvider()
        self.context_builder = ContextBuilder(system_prompt=self.system_prompt)

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

    def _messages_to_prompt(self, messages: List[Message]) -> str:
        lines = []
        for msg in messages:
            if msg.role == "system":
                lines.append(f"System: {msg.content}")
            elif msg.role == "user":
                lines.append(f"User: {msg.content}")
            elif msg.role == "assistant":
                lines.append(f"Assistant: {msg.content}")
            else:
                lines.append(f"{msg.role}: {msg.content}")
        return "\n".join(lines)

    async def update_async(self) -> Status:
        """生成/改进答案并自我评估"""
        try:
            state = self.state_manager.get()

            if state.round == 0:
                prompt_content = (
                    f"Task: {state.task}\n\n"
                    "Generate your best answer, evaluate it, and provide your score and reflection."
                )
            else:
                prompt_content = f"""Task: {state.task}

Previous Answer: {state.answer}

Previous Score: {state.score}

Feedback to address: {state.reflection}

Please improve your answer based on the feedback, then re-evaluate and provide your new score and reflection."""

            logger.debug("🤖 [{}] Round {} - 调用 Gemini...", self.name, state.round + 1)

            # Build messages
            user_msg = human(prompt_content)
            full_messages = self.context_builder.build([user_msg])
            prompt_str = self._messages_to_prompt(full_messages)

            response = await self.provider.generate_text(
                prompt_str,
                model=self.model,
                # system_instruction handled by ContextBuilder -> prompt_str
                temperature=0.7,
                timeout=60.0,
            )

            content = response.text.strip()

            if not content:
                logger.warning("⚠️ [{}] LLM 返回空响应", self.name)
                return Status.FAILURE

            answer, score, reflection = self._parse_response(content)

            if answer is None:
                logger.warning("⚠️ [{}] 无法解析 LLM 响应", self.name)
                return Status.FAILURE

            ai_msg = ai(content)
            
            # Update explicit fields AND message history
            self.state_manager.update({
                "answer": answer,
                "answer_history": [answer],
                "score": score,
                "score_history": [score],
                "reflection": reflection,
                "reflection_history": [reflection] if reflection else [],
                "messages": [user_msg, ai_msg], # Append interactions
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

        answer_match = re.search(r"Answer:\s*(.+?)(?=\n\s*Score:|$)", content, re.DOTALL | re.IGNORECASE)
        if answer_match:
            answer = answer_match.group(1).strip()

        score_match = re.search(r"Score:\s*([0-9]+(?:\.[0-9]+)?)", content, re.IGNORECASE)
        if score_match:
            try:
                score = float(score_match.group(1))
            except ValueError:
                score = 0.0

        reflection_match = re.search(r"Reflection:\s*(.+)", content, re.DOTALL | re.IGNORECASE)
        if reflection_match:
            reflection = reflection_match.group(1).strip()

        return answer, score, reflection


class IsGoodEnough(Behaviour):
    """
    条件节点：检查是否达到目标分数。
    """

    def __init__(self, name: str = "IsGoodEnough", threshold: float = 8.0, max_rounds: int = 10):
        super().__init__(name)
        self.threshold = threshold
        self.max_rounds = max_rounds
        self.state_manager = None

    def update(self) -> Status:
        if self.state_manager is None:
            logger.error("❌ [{}] state_manager 未注入", self.name)
            return Status.FAILURE

        state = self.state_manager.get()

        if state.round >= self.max_rounds:
            logger.warning("⚠️ [{}] 达到最大轮数 ({}), 强制停止", self.name, self.max_rounds)
            self.state_manager.update({"is_complete": True})
            return Status.SUCCESS

        if state.score >= self.threshold:
            logger.info("✅ [{}] Score 达标: {:.1f} >= {:.1f}", self.name, state.score, self.threshold)
            self.state_manager.update({"is_complete": True})
            return Status.SUCCESS

        logger.debug("🔄 [{}] Score 不达标: {:.1f} < {:.1f}", self.name, state.score, self.threshold)
        return Status.FAILURE
