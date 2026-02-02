"""
Reflexion Agent Demo - Self-Refine 模式（OpenAI 兼容 API）

演示如何使用 btflow 的 Reflexion 模式迭代改进输出质量。

流程：
    1. 生成初始答案
    2. 自我评估 (0-10 分)
    3. 如果分数 < 阈值，反思并改进
    4. 重复直到达标或达到最大轮数

运行方式：
    export OPENAI_API_KEY="your-api-key"
    export BASE_URL="https://your-openai-compatible-endpoint"
    python examples/reflexion_demo.py
"""
import asyncio
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from btflow.patterns.reflexion import ReflexionAgent
from btflow.llm import LLMProvider


async def demo_haiku(provider):
    """演示：生成诗歌"""
    print("\n" + "="*60)
    print("📝 Demo: Generate a Haiku")
    print("="*60 + "\n")
    
    agent = ReflexionAgent.create(
        provider=provider,
        model="gemini-2.5-flash",
        threshold=8.0,   # 分数阈值
        max_rounds=3     # 最大改进轮数
    )
    
    task = "Write a haiku about coding at midnight"
    print(f"📋 Task: {task}\n")
    
    result = await agent.run(
        input_data={"task": task},
        max_ticks=50
    )
    
    state = agent.state_manager.get()
    print(f"\n{'='*60}")
    print(f"📊 Final Status: {result}")
    print(f"💬 Final Answer:\n{state.answer}")
    print(f"⭐ Final Score: {state.score:.1f}")
    print(f"🔄 Total Rounds: {state.round}")
    
    if len(state.score_history) > 1:
        print(f"\n📈 Score Progress: {' → '.join(f'{s:.1f}' for s in state.score_history)}")


async def demo_explanation(provider):
    """演示：生成解释"""
    print("\n" + "="*60)
    print("🧠 Demo: Explain a Concept")
    print("="*60 + "\n")
    
    agent = ReflexionAgent.create(
        provider=provider,
        model="gemini-2.5-flash",
        threshold=9.8,   # 极高阈值，强制多轮改进
        max_rounds=5     # 允许更多改进
    )
    
    task = "Explain quantum computing to a 10-year-old in 3 sentences"
    print(f"📋 Task: {task}\n")
    
    result = await agent.run(
        input_data={"task": task},
        max_ticks=50
    )
    
    state = agent.state_manager.get()
    print(f"\n{'='*60}")
    print(f"💬 Final Answer:\n{state.answer}")
    print(f"⭐ Final Score: {state.score:.1f}")
    print(f"🔄 Total Rounds: {state.round}")
    
    if len(state.answer_history) > 1:
        print(f"\n📜 Improvement History:")
        for i, (ans, score) in enumerate(zip(state.answer_history, state.score_history)):
            print(f"  Round {i+1} (Score: {score:.1f}):")
            print(f"    Answer: {ans[:80]}..." if len(ans) > 80 else f"    Answer: {ans}")
            if i < len(state.reflection_history):
                ref = state.reflection_history[i]
                if ref:
                    print(f"    Reflection: {ref[:80]}..." if len(ref) > 80 else f"    Reflection: {ref}")


async def main():
    """运行演示"""
    base_url = os.getenv("BASE_URL")

    try:
        # Prefer Gemini to avoid key mismatch issues
        provider = LLMProvider.default(preference=["gemini", "openai"], base_url=base_url)
    except RuntimeError as e:
        print(str(e))
        return
    
    print("🔄 BTflow Reflexion Agent Demo (Self-Refine)")
    print("=" * 60)
    await demo_haiku(provider)


if __name__ == "__main__":
    asyncio.run(main())
