"""
Gemini Demo - 单次对话
使用 BTAgent 接口
"""
import sys
import os
import asyncio
import operator
from typing import Annotated, List
from pydantic import BaseModel, Field
import py_trees

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from btflow.state import StateManager
from btflow.runtime import ReactiveRunner
from btflow.agent import BTAgent
from btflow.nodes.llm import GeminiNode  

# === 1. 定义状态 ===
class AgentState(BaseModel):
    messages: Annotated[List[str], operator.add] = Field(default_factory=list)
    step_count: Annotated[int, operator.add] = Field(default=0)

async def main():
    print("--- ✨ Gemini Powered Agent (使用 BTAgent) ---")

    # 2. 初始化状态
    state_manager = StateManager(schema=AgentState)
    state_manager.initialize({
        "messages": [],
        "step_count": 0
    })

    # 3. 构建树 (不需要传 state_manager，Runner 会自动注入)
    root = py_trees.composites.Sequence(name="GeminiFlow", memory=True)
    gemini_node = GeminiNode(
        name="Gemini_2.5_Flash", 
        model="gemini-2.5-flash", 
        system_prompt="你是一位充满智慧的计算机科学家，擅长用优美的比喻解释技术。"
    )
    root.add_children([gemini_node])

    # 4. 创建 BTAgent 并运行
    runner = ReactiveRunner(root, state_manager)
    agent = BTAgent(runner)
    
    # 使用 agent.run() - 注入初始问题并运行
    await agent.run(
        input_data={"messages": ["User: 嗨！请用一句诗意的语言描述一下什么是'事件驱动架构'？"]},
        max_ticks=10
    )

    # 5. 打印结果
    final_state = state_manager.get()
    print("\n" + "="*30)
    print("📜 最终对话历史:")
    for msg in final_state.messages:
        print(f"- {msg}")
    print("="*30 + "\n")

if __name__ == "__main__":
    asyncio.run(main())