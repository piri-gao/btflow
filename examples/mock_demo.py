"""
Mock Demo - 演示基本的 BTflow 工作流程
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
from btflow.nodes.mock import MockLLMAction

# === 1. 定义状态 Schema ===
class AgentState(BaseModel):
    # Annotated[list, operator.add] 告诉 StateManager：
    # 当有新值写入时，执行 old_list + new_list (即 append)
    messages: Annotated[List[str], operator.add] = Field(default_factory=list)
    step_count: Annotated[int, operator.add] = Field(default=0)

async def main():
    print("--- 🏁 BTflow Demo (使用 BTAgent) ---")

    # 2. 初始化状态管理器
    state_manager = StateManager(schema=AgentState)
    state_manager.initialize({
        "messages": [],
        "step_count": 0
    })

    # 3. 构建行为树
    root = py_trees.composites.Sequence(name="MainSequence", memory=True)
    node1 = MockLLMAction(name="LLM_Node_1", state_manager=state_manager)
    node2 = MockLLMAction(name="LLM_Node_2", state_manager=state_manager)
    root.add_children([node1, node2])

    # 4. 创建 BTAgent 并运行
    runner = ReactiveRunner(root, state_manager)
    agent = BTAgent(runner)
    
    print(f"📊 初始状态: {state_manager.get().model_dump()}")
    
    # 使用 agent.run() - 注入初始消息并运行
    await agent.run(
        input_data={"messages": ["User: 你好，世界！"]},
        max_ticks=50
    )

    # 5. 验证结果
    final_state = state_manager.get()
    print("\n--- 🎉 执行结束 ---")
    print(f"📊 最终消息历史 (Messages): {final_state.messages}")
    print(f"🔢 最终步数 (Steps): {final_state.step_count}")
    
    # 简单断言验证
    assert len(final_state.messages) == 3  # 1 User + 2 AI
    assert final_state.step_count == 2     # 2个节点各加了1

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Demo interrupted.")