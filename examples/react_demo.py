"""
ReAct Agent Demo - 使用 Gemini 实现 ReAct 模式

演示如何使用 btflow 的 ReAct 模式实现一个能够使用工具的 AI Agent。

运行方式：
    # 确保设置了 GOOGLE_API_KEY 环境变量
    export GOOGLE_API_KEY="your-api-key"
    
    # 运行示例
    python examples/react_demo.py
"""
import asyncio
import operator
from typing import Annotated, List, Optional

from pydantic import BaseModel, Field
from py_trees.composites import Sequence
from py_trees.common import Status

from btflow import BTAgent, StateManager
from btflow.core.logging import logger
from btflow.patterns.tools import Tool, CalculatorTool, SearchTool
from btflow.patterns.react import (
    ReActState,
    ReActGeminiNode,
    ToolExecutor,
    CheckFinalAnswer,
    ReActAgent
)


# ============ 方式一：使用 ReActAgent.create_with_gemini（推荐）============

async def demo_react_agent_factory():
    """使用 ReActAgent 工厂快速创建 Agent"""
    print("\n" + "="*60)
    print("🚀 Demo 1: ReActAgent.create_with_gemini (推荐)")
    print("="*60 + "\n")
    
    # 创建 Agent（使用专门的 ReActGeminiNode）
    agent = ReActAgent.create_with_gemini(
        tools=[CalculatorTool(), SearchTool()],
        model="gemini-2.5-flash",
        max_rounds=10
    )
    
    question = "What is 25 multiplied by 4, then add 10?"
    print(f"👤 Question: {question}\n")
    
    # 运行 Agent
    result = await agent.run(
        input_data={"messages": [f"Question: {question}"]},
        max_ticks=100  # 最大 tick 数作为额外保护
    )
    
    # 获取结果
    state = agent.state_manager.get()
    print(f"\n📊 Final Status: {result}")
    print(f"💬 Final Answer: {state.final_answer}")
    print(f"🔄 Total Rounds: {state.round}")
    
    # 显示完整对话历史
    print("\n📜 Conversation History:")
    print("-" * 40)
    for i, msg in enumerate(state.messages):
        preview = msg[:150] + "..." if len(msg) > 150 else msg
        print(f"[{i+1}] {preview}")
        print("-" * 40)


# ============ 方式二：手动组装（更灵活）============

async def demo_manual_setup():
    """手动组装 ReAct Agent（提供更多控制）"""
    print("\n" + "="*60)
    print("🔧 Demo 2: Manual Setup")
    print("="*60 + "\n")
    
    # 1. 定义工具
    tools = [CalculatorTool(), SearchTool()]
    tool_executor = ToolExecutor(name="Tools", tools=tools)
    tools_desc = tool_executor.get_tools_description()
    
    # 2. 创建 ReAct 专用的 Gemini 节点
    llm_node = ReActGeminiNode(
        name="ReActLLM",
        model="gemini-2.5-flash",
        tools_description=tools_desc
    )
    
    check_node = CheckFinalAnswer(name="CheckAnswer", max_rounds=10)
    
    # 3. 组装行为树
    # Root (Sequence)
    # ├── 1. ReActGeminiNode → 调用 LLM（只在需要时）
    # ├── 2. ToolExecutor    → 执行工具（如果有 Action）
    # └── 3. CheckFinalAnswer → 检查是否完成
    root = Sequence(name="ReAct", memory=False, children=[
        llm_node,
        tool_executor,
        check_node
    ])
    
    # 4. 创建状态管理器
    state_manager = StateManager(schema=ReActState)
    state_manager.initialize({})
    
    # 5. 创建 Agent
    agent = BTAgent(root, state_manager)
    
    # 6. 运行
    question = "What is the capital of France? And what is 100 divided by 4?"
    print(f"👤 Question: {question}\n")
    
    result = await agent.run(
        input_data={"messages": [f"Question: {question}"]},
        max_ticks=50
    )
    
    # 7. 输出结果
    state = agent.state_manager.get()
    print(f"\n📊 Final Status: {result}")
    print(f"💬 Final Answer: {state.final_answer}")
    print(f"🔄 Total Rounds: {state.round}")
    
    # 显示完整对话历史
    print("\n📜 Conversation History:")
    print("-" * 40)
    for i, msg in enumerate(state.messages):
        preview = msg[:200] + "..." if len(msg) > 200 else msg
        print(f"[{i+1}] {preview}")
        print("-" * 40)


# ============ 方式三：自定义工具 ============

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


async def demo_custom_tools():
    """演示自定义工具"""
    print("\n" + "="*60)
    print("🌤️ Demo 3: Custom Tools")
    print("="*60 + "\n")
    
    # 使用自定义工具
    agent = ReActAgent.create_with_gemini(
        tools=[CalculatorTool(), WeatherTool()],
        model="gemini-2.5-flash",
        max_rounds=10
    )
    
    question = "What's the weather in Singapore? If the temperature is above 30, calculate 30 * 2."
    print(f"👤 Question: {question}\n")
    
    result = await agent.run(
        input_data={"messages": [f"Question: {question}"]},
        max_ticks=50
    )
    
    state = agent.state_manager.get()
    print(f"\n📊 Final Status: {result}")
    print(f"💬 Final Answer: {state.final_answer}")
    print(f"🔄 Total Rounds: {state.round}")


# ============ Main ============

async def main():
    """运行所有演示"""
    import os
    
    # 检查 API Key
    if not os.getenv("GOOGLE_API_KEY"):
        print("❌ Error: GOOGLE_API_KEY environment variable not set!")
        print("Please run: export GOOGLE_API_KEY='your-api-key'")
        return
    
    # 选择要运行的 demo
    print("🤖 BTflow ReAct Agent Demo")
    print("=" * 60)
    print("Select demo to run:")
    print("  1. ReActAgent.create_with_gemini (recommended)")
    print("  2. Manual Setup (more flexible)")
    print("  3. Custom Tools")
    print("  4. Run all demos")
    print("=" * 60)
    
    choice = input("Enter choice (1-4, default=1): ").strip() or "1"
    
    demos = {
        "1": demo_react_agent_factory,
        "2": demo_manual_setup,
        "3": demo_custom_tools,
    }
    
    if choice == "4":
        for demo in demos.values():
            await demo()
    elif choice in demos:
        await demos[choice]()
    else:
        print(f"Invalid choice: {choice}")


if __name__ == "__main__":
    asyncio.run(main())
