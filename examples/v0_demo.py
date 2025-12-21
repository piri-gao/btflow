# Demo script will go here
import sys
import os


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import operator
from typing import Annotated, List
from pydantic import BaseModel, Field
import py_trees

# 引入我们的核心组件
from btflow.state import StateManager
from btflow.runtime import ReactiveRunner
from btflow.nodes.mock import MockLLMAction

# === 1. 定义状态 Schema (就像 LangGraph) ===
class AgentState(BaseModel):
    # Annotated[list, operator.add] 告诉 StateManager：
    # 当有新值写入时，执行 old_list + new_list (即 append)
    messages: Annotated[List[str], operator.add] = Field(default_factory=list)
    
    # 普通的 int，默认是覆盖写，但如果我们也想累加，可以用 operator.add
    step_count: Annotated[int, operator.add] = Field(default=0)

async def main():
    print("--- 🏁 初始化 btflow v0 Demo ---")

    # 2. 初始化状态管理器
    state_manager = StateManager(schema=AgentState)
    state_manager.initialize({
        "messages": ["User: 你好，世界！"],
        "step_count": 0
    })

    # 3. 构建行为树
    # 使用标准的 Sequence (顺序执行)
    root = py_trees.composites.Sequence(name="MainSequence", memory=True)
    
    # 添加两个模拟 LLM 节点，串行工作
    node1 = MockLLMAction(name="LLM_Node_1", state_manager=state_manager)
    node2 = MockLLMAction(name="LLM_Node_2", state_manager=state_manager)
    
    root.add_children([node1, node2])

    # 4. 启动异步运行器
    runner = ReactiveRunner(root, state_manager)
    
    print(f"📊 初始状态: {state_manager.get().model_dump()}")
    
    # 运行！
    await runner.run(max_ticks=50, tick_interval=0.1)

    # 5. 验证结果
    final_state = state_manager.get()
    print("\n--- 🎉 执行结束 ---")
    print(f"📊 最终消息历史 (Messages): {final_state.messages}")
    print(f"🔢 最终步数 (Steps): {final_state.step_count}")
    
    # 简单断言验证
    assert len(final_state.messages) == 3 # 1 User + 2 AI
    assert final_state.step_count == 2    # 2个节点各加了1

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Demo interrupted.")