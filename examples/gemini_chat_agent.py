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
    print("\n" + "="*50)
    print("✨ Gemini ChatBot (连续对话模式)")
    print("   输入 'exit' 或 'quit' 退出")
    print("="*50)

    # === 2. 初始化 (只做一次) ===
    # 关键点：State Manager 要在循环外面初始化，这样才能记住历史
    state_manager = StateManager(schema=AgentState)
    state_manager.initialize({
        "messages": [], # 初始为空
        "step_count": 0
    })

    # === 3. 构建树 (只做一次) ===
    root = py_trees.composites.Sequence(name="GeminiFlow", memory=True)
    gemini_node = GeminiNode(
        name="Gemini", 
        state_manager=state_manager,
        model="gemini-2.5-flash", 
        system_prompt="你是一个乐于助人的 AI 助手。"
    )
    root.add_children([gemini_node])

    # 运行器也复用
    runner = ReactiveRunner(root, state_manager)

    # === 4. 进入聊天死循环 ===
    while True:
        try:
            # 获取用户输入
            user_input = input("\n👤 User: ").strip()
            
            # 退出检测
            if user_input.lower() in ["exit", "quit", "q"]:
                print("👋 Bye!")
                break
            if not user_input:
                continue

            # --- 关键步骤：把新问题追加到状态里 ---
            # 这一步会触发 State 变更 -> 唤醒 Runner
            state_manager.update({
                "messages": [f"User: {user_input}"]
            })

            # --- 运行一次思考 ---
            # 这里的 max_ticks 控制单次回复的思考长度，不是总对话轮数
            # 我们需要重置树的状态，否则它会以为任务已经做完了(SUCCESS)
            root.status = py_trees.common.Status.INVALID
            for node in root.iterate():
                node.status = py_trees.common.Status.INVALID

            # 启动运行
            await runner.run(max_ticks=10)

            # --- 打印本次回复 ---
            # 获取最新的一条消息（Gemini 的回复）
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