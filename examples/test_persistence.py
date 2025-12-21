import sys
import os
import asyncio
import operator
import shutil
from typing import Annotated, List
from pydantic import BaseModel, Field
import py_trees
from py_trees.blackboard import Client as BlackboardClient

# 路径补丁
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from btflow.state import StateManager
from btflow.runtime import ReactiveRunner
from btflow.nodes.mock import MockLLMAction
from btflow.persistence import SimpleCheckpointer

class AgentState(BaseModel):
    messages: Annotated[List[str], operator.add] = Field(default_factory=list)
    step_count: Annotated[int, operator.add] = Field(default=0)

async def run_session(thread_id="test_session_1", max_ticks=10):
    print(f"\n--- ▶️ 启动 Session (Max Ticks: {max_ticks}) ---")
    
    # 1. 初始化组件
    state_manager = StateManager(schema=AgentState)
    checkpointer = SimpleCheckpointer(storage_dir="./.checkpoints")
    
    # 初始化
    state_manager.initialize({"messages": [], "step_count": 0})

    # 2. 构建树
    root = py_trees.composites.Sequence(name="MainSeq", memory=True)
    node1 = MockLLMAction(name="Node_A", state_manager=state_manager)
    node2 = MockLLMAction(name="Node_B", state_manager=state_manager)
    root.add_children([node1, node2])

    # 3. 运行
    runner = ReactiveRunner(root, state_manager)
    await runner.run(
        max_ticks=max_ticks, 
        checkpointer=checkpointer, 
        thread_id=thread_id
    )
    
    return state_manager.get()

async def main():
    THREAD_ID = "persist_demo"
    
    # === 🧹 1. 清理存档文件 ===
    if os.path.exists(".checkpoints"):
        shutil.rmtree(".checkpoints")
        print("🧹 [Test] 旧存档已删除")

    # === 🧹 2. 关键：清理全局黑板 ===
    # py_trees 的黑板是全局单例，必须手动清除，防止 Phase 1 的数据污染 Phase 2
    print("🧹 [Test] 正在核平全局黑板...")
    blackboard = BlackboardClient(name="GlobalCleaner")
    blackboard.unregister_all_keys() # 这是一个彻底的清理

    print("\n=== 🧪 阶段 1: 运行一半 crash ===")
    # 设置为 8 ticks (约0.8s)，此时 Node A 刚完，Node B 刚开始
    await run_session(thread_id=THREAD_ID, max_ticks=8)
    
    # === 🧹 3. 再次清理全局黑板 ===
    # 确保 Phase 2 启动时，黑板里没有任何 Phase 1 留下的"僵尸数据"
    # 我们只依赖 Checkpoint 文件来恢复数据
    print("\n🧹 [Test] 再次核平全局黑板 (防止僵尸数据)...")
    blackboard.unregister_all_keys()

    print("\n=== 🧪 阶段 2: 重启恢复 ===")
    final_state = await run_session(thread_id=THREAD_ID, max_ticks=30)

    print("\n=== 📊 最终审计 ===")
    msgs = final_state.messages
    print(f"消息数量: {len(msgs)}")
    for i, m in enumerate(msgs):
        print(f"[{i}] {m}")

if __name__ == "__main__":
    asyncio.run(main())