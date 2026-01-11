import asyncio
import time
import py_trees
from py_trees.trees import BehaviourTree
from py_trees.common import Status
from py_trees.composites import Composite, Selector, Sequence
from btflow.core.behaviour import AsyncBehaviour
from btflow.core.logging import logger

class ReactiveRunner:
    """
    Runner: 支持断点续传、资源清理、状态差异化恢复。
    升级为事件驱动 (Event-Driven) 调度模式
    """
    def __init__(self, root: py_trees.behaviour.Behaviour, state_manager, setup_timeout: float = 15.0):
        self.root = root
        self.state_manager = state_manager 
        self.tree = BehaviourTree(root)
        self.tree.setup(timeout=setup_timeout)
        
        # 核心信号量：事件锁
        self.tick_signal = asyncio.Event()
        
        # Gatekeeper 开关：控制信号触发
        # step 模式下关闭（忽略内部信号），run 模式下开启
        self.auto_driving = False

        # 1. 订阅状态变化 (State Driven)
        self.state_manager.subscribe(self._on_wake_signal)

        # 2. 遍历所有节点，完成依赖注入
        for node in self.root.iterate():
            # 2a. 注入 StateManager（自动依赖注入）
            if hasattr(node, "bind_state_manager"):
                node.bind_state_manager(self.state_manager)
            elif hasattr(node, "state_manager"):
                # 对于普通的 PyTrees 节点，如果预留了 state_manager 槽位，直接注入
                node.state_manager = self.state_manager
            else:
                # 甚至可以强制注入（虽然动态语言允许这样做，但有点黑魔法）
                # 暂时选择保守策略：如果不显式声明属性或方法，可能是无状态节点
                pass
            
            # 2b. 注入唤醒回调（Task Driven）
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
        
        logger.info("🚀 [Runner] 启动 (Thread: {}) [Mode: Event-Driven]...", thread_id)
        
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

                logger.info("🔄 [Runner] 状态已恢复，继续执行...")
            else:
                logger.info("🆕 [Runner] 无存档，开始新会话...")

        # 启动时先手动触发一次，保证第一帧执行
        self.tick_signal.set()

        tick_count = 0
        start_time = time.monotonic()  # Hot loop 检测计时器
        hot_loop_warned = False  # 避免重复警告
        
        try:
            while True: # [修改] 改为死循环
                # 1. 检查最大步数限制 (仅在设置了 max_ticks 时检查)
                if max_ticks is not None and tick_count >= max_ticks:
                    logger.warning("⚠️ [Runner] 达到最大 Tick 限制 (熔断保护)，停止。")
                    break

                # 2. 等待信号
                await self.tick_signal.wait()
                self.tick_signal.clear()

                # 3. 执行 Tick
                self.tree.tick()
                tick_count += 1  # 计数
                status = self.root.status
                
                # 4. Hot Loop 检测：如果 1 秒内超过 100 次 tick，警告
                if not hot_loop_warned and tick_count >= 100:
                    elapsed = time.monotonic() - start_time
                    if elapsed < 1.0:
                        logger.warning(
                            "⚠️ [Runner] 疑似 Hot Loop: {} ticks in {:.2f}s. "
                            "检查是否有同步节点在 update() 中调用 state.update()",
                            tick_count, elapsed
                        )
                        hot_loop_warned = True
                
                # 收集状态用于存档
                current_state_data = self.state_manager.get().model_dump()
                current_tree_state = {n.name: n.status.name for n in self.root.iterate()}

                logger.debug("⏱️ [Tick {}] Root Status: {}", tick_count+1, status.name)

                if checkpointer and tick_count % checkpoint_interval == 0:
                    checkpointer.save(thread_id, tick_count, current_state_data, current_tree_state)

                if status == Status.SUCCESS:
                    logger.info("✅ [Runner] 执行成功 (SUCCESS).")
                    break
                elif status == Status.FAILURE:
                    logger.error("❌ [Runner] 执行失败 (FAILURE).")
                    break
                
                # [注意] 这里删除了原来的 if RUNNING: await sleep()
                # 只要任务还在跑，我们就在下一轮循环 await tick_signal.wait()

            else:
                logger.warning("⚠️ [Runner] 达到最大 Tick 次数，强制停止。")
                
        except asyncio.CancelledError:
            logger.warning("🛑 [Runner] 任务被外部取消。")
            raise  # Re-raise to propagate cancellation to caller
        except KeyboardInterrupt:
            logger.warning("🛑 [Runner] 用户手动中断。")
        except AssertionError as e:
            logger.error("🔥 [Runner] 树结构状态异常: {}", e)
            raise e
        finally:
            self.auto_driving = False  # 关闭自动驾驶
            logger.debug("🧹 [Runner] 正在清理资源...")
            # 取消订阅，防止内存泄漏
            self.state_manager.unsubscribe(self._on_wake_signal)
            # 解绑节点的唤醒回调，防止 Long-lived Tree 场景下的引用泄漏
            for node in self.root.iterate():
                if isinstance(node, AsyncBehaviour):
                    node.bind_wake_up(None)
            self.tree.interrupt()
            logger.info("💤 [Runner] 结束。")