"""
LLM ChatBot (连续对话模式)
使用 BTAgent 接口进行多轮对话
"""
import sys
import os
import asyncio
import operator
from typing import Annotated, List
from pydantic import BaseModel, Field
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Reduce log noise during streaming output
os.environ.setdefault("BTFLOW_LOG_LEVEL", "WARNING")

# 一行 import 搞定！
from btflow import BTAgent, StateManager, Sequence
from btflow.nodes import LLMNode
from btflow.llm import LLMProvider

# === 1. 定义状态 ===
class AgentState(BaseModel):
    messages: Annotated[List[str], operator.add] = Field(default_factory=list)
    step_count: Annotated[int, operator.add] = Field(default=0)
    streaming_output: str = ""

async def main():
    print("\n" + "="*50)
    print("✨ LLM ChatBot (使用 BTAgent)")
    print("   输入 'exit' 或 'quit' 退出")
    print("="*50)

    # === 2. 初始化 ===
    state_manager = StateManager(schema=AgentState)
    state_manager.initialize({
        "messages": [],
        "step_count": 0
    })

    # === 3. 构建树 (不需要传 state_manager，Runner 会自动注入) ===
    root = Sequence(name="LLMFlow", memory=True)
    try:
        provider = LLMProvider.default(preference=["gemini", "openai"], base_url=os.getenv("BASE_URL"))
    except RuntimeError as e:
        print(str(e))
        return
    llm_node = LLMNode(
        name="ChatLLM",
        provider=provider,
        model="gemini-2.5-flash",
        system_prompt="你是一个乐于助人的 AI 助手。",
        assistant_prefix="Assistant",
        step_key="step_count",
        stream=True,
        streaming_output_key="streaming_output",
    )
    root.add_children([llm_node])

    # === 4. 创建 BTAgent (无需手动创建 Runner！) ===
    agent = BTAgent(root, state_manager)

    # === 5. 进入聊天循环 ===
    last_stream = ""
    streaming_active = False
    def on_state_change():
        nonlocal last_stream, streaming_active
        if not streaming_active:
            return
        current = state_manager.get().streaming_output
        if current and current != last_stream:
            delta = current[len(last_stream):]
            if delta:
                print(delta, end="", flush=True)
            last_stream = current

    state_manager.subscribe(on_state_change)
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
            # Print assistant prefix for streaming
            last_stream = ""
            streaming_active = True
            print("🤖 ", end="", flush=True)

            await agent.run(
                input_data={"messages": [f"User: {user_input}"], "streaming_output": ""},
                reset_tree=True,
                reset_data=False,
                max_ticks=10
            )
            streaming_active = False

            # 打印本次回复
            current_msgs = state_manager.get().messages
            if current_msgs and current_msgs[-1].startswith("Assistant:"):
                if last_stream:
                    print()
                else:
                    print(f"🤖 {current_msgs[-1]}")
                last_stream = ""

        except KeyboardInterrupt:
            print("\n👋 用户强制退出")
            break
        except Exception as e:
            print(f"❌ 发生错误: {e}")

if __name__ == "__main__":
    asyncio.run(main())
