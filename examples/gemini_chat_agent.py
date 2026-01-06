"""
Gemini ChatBot (连续对话模式)
使用 BTAgent 接口进行多轮对话
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
    print("\n" + "="*50)
    print("✨ Gemini ChatBot (使用 BTAgent)")
    print("   输入 'exit' 或 'quit' 退出")
    print("="*50)

    # === 2. 初始化 ===
    state_manager = StateManager(schema=AgentState)
    state_manager.initialize({
        "messages": [],
        "step_count": 0
    })

    # === 3. 构建树 ===
    root = py_trees.composites.Sequence(name="GeminiFlow", memory=True)
    gemini_node = GeminiNode(
        name="Gemini", 
        state_manager=state_manager,
        model="gemini-2.5-flash", 
        system_prompt="你是一个乐于助人的 AI 助手。"
    )
    root.add_children([gemini_node])

    # === 4. 创建 BTAgent ===
    runner = ReactiveRunner(root, state_manager)
    agent = BTAgent(runner)

    # === 5. 进入聊天循环 ===
    while True:
        try:
            user_input = input("\n👤 User: ").strip()
            
            if user_input.lower() in ["exit", "quit", "q"]:
                print("👋 Bye!")
                break
            if not user_input:
                continue

            # 使用 BTAgent.run() - 自动处理树状态重置
            # reset_tree=True: 从根节点开始新决策
            # reset_data=False: 保留 messages 历史
            await agent.run(
                input_data={"messages": [f"User: {user_input}"]},
                reset_tree=True,
                reset_data=False,
                max_ticks=10
            )

            # 打印本次回复
            current_msgs = state_manager.get().messages
            if current_msgs and current_msgs[-1].startswith("Gemini:"):
                print(f"🤖 {current_msgs[-1]}")

        except KeyboardInterrupt:
            print("\n👋 用户强制退出")
            break
        except Exception as e:
            print(f"❌ 发生错误: {e}")

if __name__ == "__main__":
    asyncio.run(main())