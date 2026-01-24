"""
ReAct Agent Demo - 使用 Gemini 实现 ReAct 模式

演示如何使用 btflow 的 ReAct 模式实现一个能够使用工具的 AI Agent。

Tree Structure (使用 btflow.LoopUntilSuccess):
    Root (LoopUntilSuccess)
    └── Sequence (memory=True)
        ├── ReActLLMNode       → 调用 LLM
        ├── ToolExecutor       → 执行工具
        └── IsFinalAnswer      → 条件检查 (SUCCESS=结束, FAILURE=继续)

运行方式：
    export GOOGLE_API_KEY="your-api-key"
    python examples/react_demo.py
"""
import asyncio
import os

from btflow.tools import Tool, CalculatorTool, SearchTool
from btflow.patterns.react import ReActAgent
from btflow.llm import GeminiProvider
from btflow.messages import human


# ============ 自定义工具 ============

class WeatherTool(Tool):
    """自定义天气查询工具（模拟）"""
    name = "weather"
    description = "Get the current weather for a city. Input should be a city name."
    
    _mock_weather = {
        "singapore": "Sunny, 32°C, Humidity 75%",
        "tokyo": "Cloudy, 22°C, Humidity 60%",
        "new york": "Rainy, 15°C, Humidity 85%",
        "london": "Foggy, 12°C, Humidity 90%",
        "paris": "Clear, 18°C, Humidity 55%",
    }
    
    def run(self, input: str) -> str:
        city = input.lower().strip()
        if city in self._mock_weather:
            return f"Weather in {input}: {self._mock_weather[city]}"
        return f"Weather data not available for {input}. This is a mock service."


# ============ Demo Functions ============

async def demo_calculator():
    """演示计算工具"""
    print("\n" + "="*60)
    print("🧮 Demo: Calculator Tool")
    print("="*60 + "\n")
    
    agent = ReActAgent.create(
        provider=GeminiProvider(),
        tools=[CalculatorTool()],
        model="gemini-2.5-flash",
        max_rounds=10
    )
    
    question = "What is 25 multiplied by 4, then add 10?"
    print(f"👤 Question: {question}\n")
    
    result = await agent.run(
        input_data={"messages": [human(f"Question: {question}")]},
        max_ticks=100
    )
    
    state = agent.state_manager.get()
    print(f"\n📊 Final Status: {result}")
    print(f"💬 Final Answer: {state.final_answer}")
    print(f"🔄 Total Rounds: {state.round}")
    
    print("\n📜 Conversation:")
    print("-" * 40)
    for i, msg in enumerate(state.messages):
        role_label = msg.role.upper()
        content = msg.content
        preview = content[:150] + "..." if len(content) > 150 else content
        print(f"[{i+1}][{role_label}] {preview}")
        print("-" * 40)


async def demo_multi_tools():
    """演示多工具组合"""
    print("\n" + "="*60)
    print("🛠️ Demo: Multiple Tools")
    print("="*60 + "\n")
    
    agent = ReActAgent.create(
        provider=GeminiProvider(),
        tools=[CalculatorTool(), WeatherTool()],
        model="gemini-2.5-flash",
        max_rounds=10
    )
    
    question = "What's the weather in Singapore? If the temperature is above 30, calculate 30 * 2."
    print(f"👤 Question: {question}\n")
    
    result = await agent.run(
        input_data={"messages": [human(f"Question: {question}")]},
        max_ticks=100
    )
    
    state = agent.state_manager.get()
    print(f"\n📊 Final Status: {result}")
    print(f"💬 Final Answer: {state.final_answer}")
    print(f"🔄 Total Rounds: {state.round}")


# ============ Main ============

async def main():
    """运行演示"""
    if not os.getenv("GOOGLE_API_KEY"):
        print("❌ Error: GOOGLE_API_KEY environment variable not set!")
        print("Please run: export GOOGLE_API_KEY='your-api-key'")
        return
    
    print("🤖 BTflow ReAct Agent Demo (LoopUntilSuccess Pattern)")
    print("=" * 60)
    print("Select demo to run:")
    print("  1. Calculator Tool")
    print("  2. Multiple Tools (Calculator + Weather)")
    print("  3. Run all demos")
    print("=" * 60)
    
    choice = input("Enter choice (1-3, default=1): ").strip() or "1"
    
    demos = {
        "1": demo_calculator,
        "2": demo_multi_tools,
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
