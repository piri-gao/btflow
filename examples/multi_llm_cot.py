"""
多 LLM 协作示例：CoT Chain（思维链）

展示 Planner → Executor → Reviewer 三阶段推理模式
使用真实的 Gemini API 调用

使用前请确保设置环境变量：
    export GOOGLE_API_KEY="your-api-key"
"""
import sys
import os
import asyncio
import operator
from typing import Annotated, List
from pydantic import BaseModel, Field
from dotenv import load_dotenv
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 统一 import
from btflow import BTAgent, StateManager, Sequence, AsyncBehaviour, Status

# 引入 Google GenAI SDK
from google import genai
from google.genai import types

load_dotenv()


# === 1. 定义状态 Schema ===
class CoTState(BaseModel):
    question: str = ""
    plan: str = ""
    answer: str = ""
    review: str = ""
    trace: Annotated[List[str], operator.add] = Field(default_factory=list)


# === 2. Gemini 客户端工厂 ===
def get_gemini_client():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("❌ GOOGLE_API_KEY not found! Please set it in .env or environment.")
    return genai.Client(api_key=api_key)


# === 3. 定义 LLM 节点 ===

class PlannerNode(AsyncBehaviour):
    """第一阶段：分析问题，制定计划"""
    
    def __init__(self, name: str, model: str = "gemini-2.5-flash"):
        super().__init__(name)
        self.state_manager: StateManager = None
        self.model = model
        self.client = get_gemini_client()
    
    async def update_async(self) -> Status:
        state = self.state_manager.get()
        question = state.question
        
        print(f"\n🧠 [Planner] 正在分析问题...")
        
        try:
            response = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=self.model,
                    contents=f"请分析以下问题并制定解答计划（用中文回答）：\n\n{question}",
                    config=types.GenerateContentConfig(
                        system_instruction="你是一位擅长分析问题的专家。请分解问题，制定清晰的解答计划（3-5个步骤）。",
                        temperature=0.7
                    )
                ),
                timeout=30.0
            )
            
            plan = response.text
            self.state_manager.update({
                "plan": plan,
                "trace": ["[Planner] ✅ 计划生成完成"]
            })
            
            print(f"📋 [Planner] 计划:\n{plan[:200]}...")
            return Status.SUCCESS
            
        except Exception as e:
            print(f"🔥 [Planner] 失败: {e}")
            return Status.FAILURE


class ExecutorNode(AsyncBehaviour):
    """第二阶段：执行计划，生成答案"""
    
    def __init__(self, name: str, model: str = "gemini-2.5-flash"):
        super().__init__(name)
        self.state_manager: StateManager = None
        self.model = model
        self.client = get_gemini_client()
    
    async def update_async(self) -> Status:
        state = self.state_manager.get()
        question = state.question
        plan = state.plan
        
        print(f"\n⚙️ [Executor] 正在执行计划...")
        
        try:
            prompt = f"""
问题：{question}

已制定的计划：
{plan}

请按照计划逐步解答问题（用中文回答）：
"""
            response = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction="你是一位知识渊博的老师。请按照给定的计划，逐步推理并给出详细的答案。",
                        temperature=0.5
                    )
                ),
                timeout=60.0
            )
            
            answer = response.text
            self.state_manager.update({
                "answer": answer,
                "trace": ["[Executor] ✅ 答案生成完成"]
            })
            
            print(f"✅ [Executor] 答案:\n{answer[:200]}...")
            return Status.SUCCESS
            
        except Exception as e:
            print(f"🔥 [Executor] 失败: {e}")
            return Status.FAILURE


class ReviewerNode(AsyncBehaviour):
    """第三阶段：检查答案，给出评价"""
    
    def __init__(self, name: str, model: str = "gemini-2.5-flash"):
        super().__init__(name)
        self.state_manager: StateManager = None
        self.model = model
        self.client = get_gemini_client()
    
    async def update_async(self) -> Status:
        state = self.state_manager.get()
        question = state.question
        answer = state.answer
        
        print(f"\n🔍 [Reviewer] 正在审查答案...")
        
        try:
            prompt = f"""
原始问题：{question}

给出的答案：
{answer}

请从以下角度审查答案，并给出评价（用中文回答）：
1. 逻辑性：推理过程是否清晰
2. 完整性：是否覆盖了问题的主要方面
3. 准确性：结论是否正确
4. 综合评分：优秀/良好/一般/需改进
"""
            response = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction="你是一位严谨的审查专家。请客观评估答案质量，指出优点和可改进之处。",
                        temperature=0.3
                    )
                ),
                timeout=30.0
            )
            
            review = response.text
            self.state_manager.update({
                "review": review,
                "trace": ["[Reviewer] ✅ 审查完成"]
            })
            
            print(f"📝 [Reviewer] 评价:\n{review[:200]}...")
            return Status.SUCCESS
            
        except Exception as e:
            print(f"🔥 [Reviewer] 失败: {e}")
            return Status.FAILURE


async def main():
    print("=" * 60)
    print("🔗 多 LLM 协作示例：CoT Chain（思维链）")
    print("=" * 60)
    
    # 初始化
    state_manager = StateManager(schema=CoTState)
    state_manager.initialize()
    
    # 构建 CoT Chain
    root = Sequence(name="CoT_Chain", memory=True)
    
    planner = PlannerNode("Planner")
    executor = ExecutorNode("Executor")
    reviewer = ReviewerNode("Reviewer")
    
    root.add_children([planner, executor, reviewer])
    
    # 创建 Agent (无需手动创建 Runner)
    agent = BTAgent(root, state_manager)
    
    # 运行
    question = "为什么天空是蓝色的？"
    print(f"\n❓ 用户问题: {question}\n")
    
    await agent.run(
        input_data={"question": question},
        max_ticks=20
    )
    
    # 输出完整结果
    final = state_manager.get()
    print("\n" + "=" * 60)
    print("📊 CoT Chain 执行完成")
    print("=" * 60)
    print(f"\n📋 计划:\n{final.plan}\n")
    print(f"{'='*40}")
    print(f"\n✅ 答案:\n{final.answer}\n")
    print(f"{'='*40}")
    print(f"\n📝 评价:\n{final.review}\n")
    print(f"{'='*40}")
    print(f"\n🔗 执行轨迹: {final.trace}")


if __name__ == "__main__":
    asyncio.run(main())
