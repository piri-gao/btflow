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
from btflow.nodes.llm import GeminiNode  

# === 1. 定义状态 ===
class AgentState(BaseModel):
    messages: Annotated[List[str], operator.add] = Field(default_factory=list)
    step_count: Annotated[int, operator.add] = Field(default=0)

async def main():
    print("--- ✨ 初始化 Gemini Powered Agent (Event-Driven) ---")

    # 2. 初始化状态
    state_manager = StateManager(schema=AgentState)
    state_manager.initialize({
        "messages": ["User: 嗨！请用一句诗意的语言描述一下什么是'事件驱动架构'？"],
        "step_count": 0
    })

    # 3. 构建树
    root = py_trees.composites.Sequence(name="GeminiFlow", memory=True)
    
    # 实例化 Gemini 节点
    gemini_node = GeminiNode(
        name="Gemini_2.5_Flash", 
        state_manager=state_manager,
        model="gemini-2.5-flash", 
        system_prompt="你是一位充满智慧的计算机科学家，擅长用优美的比喻解释技术。"
    )
    
    root.add_children([gemini_node])

    # 4. 运行 
    runner = ReactiveRunner(root, state_manager)
    
    # max_ticks=10 足够了，因为 Gemini 回复一次就结束了
    await runner.run(max_ticks=10) 

    final_state = state_manager.get()
    print("\n" + "="*30)
    print("📜 最终对话历史:")
    for msg in final_state.messages:
        print(f"- {msg}")
    print("="*30 + "\n")

if __name__ == "__main__":
    asyncio.run(main())