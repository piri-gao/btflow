import asyncio
import py_trees
from py_trees.trees import BehaviourTree
from py_trees.common import Status
from py_trees.composites import Composite, Selector, Sequence
from btflow.core import AsyncBehaviour

class ReactiveRunner:
    """
    Runner: 支持断点续传、资源清理、状态差异化恢复。
    升级为事件驱动 (Event-Driven) 调度模式
    """
    def __init__(self, root: py_trees.behaviour.Behaviour, state_manager):
        self.root = root
        self.state_manager = state_manager 
        self.tree = BehaviourTree(root)
        self.tree.setup(timeout=15)
        
        # 核心信号量：事件锁
        self.tick_signal = asyncio.Event()
        
        # Gatekeeper 开关：控制信号触发
        # step 模式下关闭（忽略内部信号），run 模式下开启
        self.auto_driving = False

        # 1. 订阅状态变化 (State Driven)
        self.state_manager.subscribe(self._on_wake_signal)

        # 2. 订阅所有异步节点的任务完成事件 (Task Driven)
        for node in self.root.iterate():
            if isinstance(node, AsyncBehaviour):
                node.bind_wake_up(self._on_wake_signal)

    def _on_wake_signal(self):
        """任何风吹草动，都会调用这个方法"""
        # Gatekeeper：只有在 auto_driving 模式下才触发信号
        if not self.auto_driving:
            return
        # 触发 Event，唤醒正在 wait 的 run 循环
        # 注意：asyncio.Event 是线程安全的（在同个 Loop 内），如果是多线程需用 call_soon_threadsafe
        self.tick_signal.set()
    
    def tick_once(self) -> Status:
        """
        原子 tick：执行一次行为树 tick。
        供 BTAgent.step() 同步调用，不涉及信号机制。
        """
        self.tree.tick()
        return self.root.status

    async def run(self, 
                  max_ticks: int = None, 
                  checkpointer = None,
                  checkpoint_interval: int = 1,
                  thread_id: str = "default_thread"):
        """
        事件驱动模式运行。
        
        Args:
            max_ticks: 最大 tick 次数（熔断保护）
            checkpointer: 检查点管理器
            checkpoint_interval: 保存检查点的间隔（每 N 次 tick 保存一次，默认 1）
            thread_id: 会话线程 ID
        """
        
        print(f"🚀 [Runner] 启动 (Thread: {thread_id}) [Mode: Event-Driven]...")
        
        # 开启自动驾驶模式
        self.auto_driving = True
        
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

        # 启动时先手动触发一次，保证第一帧执行
        self.tick_signal.set()

        tick_count = 0
        
        try:
            while True: # [修改] 改为死循环
                # 1. 检查最大步数限制 (仅在设置了 max_ticks 时检查)
                if max_ticks is not None and tick_count >= max_ticks:
                    print("⚠️ [Runner] 达到最大 Tick 限制 (熔断保护)，停止。")
                    break

                # 2. 等待信号
                await self.tick_signal.wait()
                self.tick_signal.clear()

                # 3. 执行 Tick
                self.tree.tick()
                tick_count += 1  # 计数
                status = self.root.status
                
                # 收集状态用于存档
                current_state_data = self.state_manager.get().model_dump()
                current_tree_state = {n.name: n.status.name for n in self.root.iterate()}

                print(f"⏱️ [Tick {tick_count+1}] Root Status: {status.name}")

                if checkpointer and tick_count % checkpoint_interval == 0:
                    checkpointer.save(thread_id, tick_count, current_state_data, current_tree_state)

                if status == Status.SUCCESS:
                    print("✅ [Runner] 执行成功 (SUCCESS).")
                    break
                elif status == Status.FAILURE:
                    print("❌ [Runner] 执行失败 (FAILURE).")
                    break
                
                # [注意] 这里删除了原来的 if RUNNING: await sleep()
                # 只要任务还在跑，我们就在下一轮循环 await tick_signal.wait()

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
            self.auto_driving = False  # 关闭自动驾驶
            print("🧹 [Runner] 正在清理资源...")
            self.tree.interrupt()
            print("💤 [Runner] 结束。")