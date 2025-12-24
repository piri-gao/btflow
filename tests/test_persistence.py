import sys
import os
import asyncio
import shutil
import operator
from typing import Annotated, List, Dict, Any
from pydantic import BaseModel, Field

# === 环境配置 ===
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from py_trees.common import Status
from py_trees.blackboard import Client as BlackboardClient
import py_trees

from btflow.core import AsyncBehaviour
from btflow.state import StateManager
from btflow.runtime import ReactiveRunner
from btflow.persistence import SimpleCheckpointer

# === 1. 定义测试用 State ===
class AgentState(BaseModel):
    messages: Annotated[List[str], operator.add] = Field(default_factory=list)
    step_count: int = 0

# === 2. 定义受控节点 (核心) ===
class ControlledAction(AsyncBehaviour):
    """
    一个完全受控的节点。
    它不依赖时间(sleep)，而是依赖外部信号(Event)来决定何时开始、何时结束。
    """
    def __init__(self, name: str, state_manager: StateManager, 
                 start_event: asyncio.Event, finish_event: asyncio.Event):
        super().__init__(name)
        self.state_manager = state_manager
        # 信号灯
        self.start_event = start_event   # 绿灯：告诉外界“我跑起来了”
        self.finish_event = finish_event # 红灯：外界控制“你可以结束了”

    async def update_async(self) -> Status:
        # 1. 发出信号：告诉测试主控，我已经进入运行状态
        print(f"   🚦 [{self.name}] 启动! 发送 start 信号...")
        self.start_event.set()
        
        # 2. 等待信号：死等主控放行
        print(f"   ⏳ [{self.name}] 挂起，等待放行信号...")
        await self.finish_event.wait()
        
        # 3. 只有收到信号后，才会执行业务逻辑
        print(f"   🟢 [{self.name}] 收到放行信号，继续执行!")
        self.state_manager.update({
            "messages": [f"{self.name} 完成了"]
        })
        return Status.SUCCESS

# === 3. 辅助函数：清理环境 ===
def cleanup_environment():
    print("🧹 [Cleanup] 清理 checkpoints 和黑板...")
    if os.path.exists(".checkpoints"):
        shutil.rmtree(".checkpoints")
    # 彻底清除全局黑板，防止内存残留
    BlackboardClient(name="Cleaner").unregister_all_keys()

# === 4. 测试流程 ===
async def test_stable_persistence():
    cleanup_environment()
    db_path = "./.checkpoints"
    thread_id = "stable_test_v1"
    
    # -------------------------------------------------------------
    # 🧪 阶段 1: 启动 -> 确认运行 -> 强制 Crash
    # -------------------------------------------------------------
    print("\n=== 🧪 阶段 1: 必死局 (Crash) ===")
    
    # 初始化信号 (Phase 1 专用)
    p1_start_event = asyncio.Event()
    p1_finish_event = asyncio.Event() # 永远不会被 set，模拟卡死
    
    # 构建树
    state_mgr_1 = StateManager(schema=AgentState)
    state_mgr_1.initialize({"messages": []})
    
    root_1 = py_trees.composites.Sequence(name="MainSeq", memory=True)
    # 这个节点会卡住
    node_1 = ControlledAction("Node_Crash", state_mgr_1, p1_start_event, p1_finish_event)
    root_1.add_child(node_1)
    
    checkpointer_1 = SimpleCheckpointer(storage_dir=db_path)
    runner_1 = ReactiveRunner(root_1, state_mgr_1)
    
    # 启动 Runner (作为后台 Task)
    # 我们给它无限的 ticks，因为它会被我们手动 cancel
    task_1 = asyncio.create_task(
        runner_1.run(max_ticks=1000, checkpointer=checkpointer_1, thread_id=thread_id)
    )
    
    print("👀 [Main] 等待节点启动...")
    # 【关键】等待节点真正运行起来。如果这里通过，说明节点肯定在 RUNNING 状态
    await asyncio.wait_for(p1_start_event.wait(), timeout=5.0)
    print("✅ [Main] 捕捉到节点已运行! 此时它正卡在 await finish_event...")

    # 稍微等一小会儿确保状态被保存 (Tick 间隔默认 0.1s)
    await asyncio.sleep(0.3)
    
    print("⚡ [Main] 执行核打击 (模拟断电/Crash)...")
    task_1.cancel() # 强制取消任务
    try:
        await task_1
    except asyncio.CancelledError:
        print("💀 [Main] Runner 1 已被强制终止。")

    # -------------------------------------------------------------
    # 🧪 阶段 2: 恢复 -> 确认重启 -> 放行完成
    # -------------------------------------------------------------
    print("\n=== 🧪 阶段 2: 复活局 (Recovery) ===")
    
    # 再次清理内存 (模拟进程重启)
    BlackboardClient(name="Cleaner").unregister_all_keys()
    
    # 初始化信号 (Phase 2 专用)
    p2_start_event = asyncio.Event()
    p2_finish_event = asyncio.Event() # 这次我们会 set 它
    
    # 重新构建树 (模拟重新加载代码)
    state_mgr_2 = StateManager(schema=AgentState)
    # 注意：这里不需要手动 initialize 数据，runner 会从 checkpoint 加载
    
    root_2 = py_trees.composites.Sequence(name="MainSeq", memory=True)
    # 使用新的事件对象
    node_2 = ControlledAction("Node_Crash", state_mgr_2, p2_start_event, p2_finish_event)
    root_2.add_child(node_2)
    
    checkpointer_2 = SimpleCheckpointer(storage_dir=db_path)
    runner_2 = ReactiveRunner(root_2, state_mgr_2)
    
    # 启动 Runner 2
    print("🚀 [Main] 启动 Runner 2 (尝试恢复)...")
    task_2 = asyncio.create_task(
        runner_2.run(max_ticks=20, checkpointer=checkpointer_2, thread_id=thread_id)
    )
    
    print("👀 [Main] 等待节点从断点恢复运行...")

    # Checkpointer 加载 -> 发现 Node_Crash 是 RUNNING -> 标记为 INVALID
    # Runner Tick -> 发现 INVALID -> 重新执行 initialise -> 重新执行 update_async
    # 所以我们会再次收到 start 信号
    try:
        await asyncio.wait_for(p2_start_event.wait(), timeout=5.0)
        print("✅ [Main] 节点已成功恢复，并重新进入运行状态!")
    except asyncio.TimeoutError:
        print("❌ [Fail] 节点没有恢复运行 (可能 Checkpoint 没存上?)")
        task_2.cancel()
        return

    # 现在放行，让它跑完
    print("🟢 [Main] 发送放行信号 (Unblock)...")
    p2_finish_event.set()
    
    # 等待任务正常结束
    await task_2
    print("🎉 [Main] 阶段 2 执行完毕。")
    
    # -------------------------------------------------------------
    # 📊 结果审计
    # -------------------------------------------------------------
    final_state = state_mgr_2.get()
    print("\n=== 📊 最终审计 ===")
    print(f"Messages: {final_state.messages}")
    
    # 行为预期：
    # 因为 Phase 1 Crash 时，节点还没运行到 "写入消息" 那一行就被杀了。
    # 所以 Phase 2 恢复后重跑，最终应该只有 1 条消息。
    # 如果 Phase 1 是在"写完消息后、保存状态前" Crash 的，那就会有重复。
    # 但由于我们的 ControlledAction 是"先等信号再写消息"，所以 Phase 1 绝对写不了消息。
    # 这是一个干净的测试。
    
    if len(final_state.messages) == 1:
        print("✅ 测试通过: 状态完美恢复，且流程执行完毕。")
    else:
        print(f"❌ 测试失败: 消息数量不符合预期 ({len(final_state.messages)})")

if __name__ == "__main__":
    try:
        asyncio.run(test_stable_persistence())
    except KeyboardInterrupt:
        pass