import asyncio
import py_trees
from py_trees.trees import BehaviourTree
from py_trees.common import Status
from py_trees.composites import Composite, Selector, Sequence

class ReactiveRunner:
    """
    Runner: 支持断点续传、资源清理、状态差异化恢复。
    """
    def __init__(self, root: py_trees.behaviour.Behaviour, state_manager):
        self.root = root
        self.state_manager = state_manager 
        self.tree = BehaviourTree(root)
        self.tree.setup(timeout=15) 

    async def run(self, 
                  max_ticks: int = 100, 
                  tick_interval: float = 0.1, 
                  checkpointer = None, 
                  thread_id: str = "default_thread"):
        
        print(f"🚀 [Runner] 启动 (Thread: {thread_id})...")
        
        if checkpointer:
            checkpoint = checkpointer.load_latest(thread_id)
            if checkpoint:
                # 1. 恢复数据
                self.state_manager.initialize(checkpoint.state_dump)
                tree_state = checkpoint.tree_state
                
                nodes_by_name = {n.name: n for n in self.root.iterate()}

                # 2. 恢复状态 (差异化策略)
                for name, status_str in tree_state.items():
                    if name in nodes_by_name:
                        node = nodes_by_name[name]
                        
                        if status_str == "SUCCESS":
                            node.status = Status.SUCCESS
                        elif status_str == "FAILURE":
                            node.status = Status.FAILURE
                        elif status_str == "RUNNING":
                            # 组合节点 -> 恢复 RUNNING
                            # 行为节点 -> 降级 INVALID (触发重试)
                            if isinstance(node, Composite):
                                node.status = Status.RUNNING
                            else:
                                node.status = Status.INVALID

                # 3. 修复 Composite 指针
                for node in self.root.iterate():
                    if isinstance(node, Composite) and node.status == Status.RUNNING:
                        target_child = None
                        for child in node.children:
                            if isinstance(node, Sequence):
                                if child.status != Status.SUCCESS:
                                    target_child = child
                                    break
                            elif isinstance(node, Selector):
                                if child.status != Status.FAILURE:
                                    target_child = child
                                    break
                            else:
                                if child.status in (Status.INVALID, Status.RUNNING):
                                    target_child = child
                                    break
                        
                        if target_child:
                            node.current_child = target_child
                        else:
                            node.stop(Status.INVALID)

                print("🔄 [Runner] 状态已恢复，继续执行...")
            else:
                print("🆕 [Runner] 无存档，开始新会话...")

        try:
            for i in range(max_ticks):
                self.tree.tick()
                status = self.root.status
                
                # 收集状态用于存档
                current_state_data = self.state_manager.get().model_dump()
                current_tree_state = {n.name: n.status.name for n in self.root.iterate()}

                print(f"⏱️ [Tick {i+1}] Root Status: {status.name}")

                if checkpointer:
                    checkpointer.save(thread_id, i+1, current_state_data, current_tree_state)

                if status == Status.SUCCESS:
                    print("✅ [Runner] 执行成功 (SUCCESS).")
                    break
                elif status == Status.FAILURE:
                    print("❌ [Runner] 执行失败 (FAILURE).")
                    break
                
                if status == Status.RUNNING:
                    await asyncio.sleep(tick_interval)
            else:
                print("⚠️ [Runner] 达到最大 Tick 次数，强制停止。")
                
        except asyncio.CancelledError:
            print("🛑 [Runner] 任务被外部取消。")
        except KeyboardInterrupt:
            print("🛑 [Runner] 用户手动中断。")
        except AssertionError as e:
            print(f"🔥 [Runner] 树结构状态异常: {e}")
            raise e
        finally:
            print("🧹 [Runner] 正在清理资源...")
            self.tree.interrupt()
            print("💤 [Runner] 结束。")