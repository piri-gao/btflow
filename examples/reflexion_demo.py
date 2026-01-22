"""
Reflexion Agent Demo - Self-Refine 模式

演示如何使用 btflow 的 Reflexion 模式迭代改进输出质量。

流程：
    1. 生成初始答案
    2. 自我评估 (0-10 分)
    3. 如果分数 < 阈值，反思并改进
    4. 重复直到达标或达到最大轮数

运行方式：
    export GOOGLE_API_KEY="your-api-key"
    python examples/reflexion_demo.py
"""
import asyncio
import os

from btflow.patterns.reflexion import ReflexionAgent


async def demo_haiku():
    """演示：生成诗歌"""
    print("\n" + "="*60)
    print("📝 Demo: Generate a Haiku")
    print("="*60 + "\n")
    
    agent = ReflexionAgent.create_with_gemini(
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


async def demo_explanation():
    """演示：生成解释"""
    print("\n" + "="*60)
    print("🧠 Demo: Explain a Concept")
    print("="*60 + "\n")
    
    agent = ReflexionAgent.create_with_gemini(
        model="gemini-2.5-flash",
        threshold=8.5,   # 较高阈值
        max_rounds=4     # 允许更多改进
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
            print(f"  Round {i+1} (Score: {score:.1f}): {ans[:80]}...")


async def main():
    """运行演示"""
    if not os.getenv("GOOGLE_API_KEY"):
        print("❌ Error: GOOGLE_API_KEY environment variable not set!")
        print("Please run: export GOOGLE_API_KEY='your-api-key'")
        return
    
    print("🔄 BTflow Reflexion Agent Demo (Self-Refine)")
    print("=" * 60)
    print("Select demo to run:")
    print("  1. Generate a Haiku")
    print("  2. Explain a Concept")
    print("  3. Run all demos")
    print("=" * 60)
    
    choice = input("Enter choice (1-3, default=1): ").strip() or "1"
    
    demos = {
        "1": demo_haiku,
        "2": demo_explanation,
    }
    
    if choice == "3":
        for demo in demos.values():
            await demo()
    elif choice in demos:
        await demos[choice]()
    else:
        print(f"Invalid choice: {choice}")


if __name__ == "__main__":
    asyncio.run(main())
