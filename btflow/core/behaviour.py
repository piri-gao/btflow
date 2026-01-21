import asyncio
from typing import Callable, Optional, TYPE_CHECKING
import py_trees
from py_trees.common import Status
from btflow.core.logging import logger

if TYPE_CHECKING:
    from btflow.core.state import StateManager

class AsyncBehaviour(py_trees.behaviour.Behaviour):
    """
    btflow 核心基类：异步行为节点。
    
    子类必须实现 update_async() 方法。
    
    Structured Concurrency 约束:
        - update_async() 中创建的所有协程必须在返回前 await 完成
        - 禁止 fire-and-forget 模式（asyncio.create_task 后不 await）
        - 如需并行执行，请在行为树中使用 Parallel 节点
    """

    def __init__(self, name: str):
        super().__init__(name)
        self.async_task = None 
        # 唤醒回调句柄
        self._wake_callback: Optional[Callable[[], None]] = None
        # StateManager 引用（由 Runner 自动注入）
        self.state_manager: Optional['StateManager'] = None

    def bind_wake_up(self, callback: Callable[[], None]):
        """绑定唤醒回调 (通常由 Runner 注入)"""
        self._wake_callback = callback

    def bind_state_manager(self, state_manager: 'StateManager'):
        """绑定 StateManager (由 Runner 自动注入)
        
        Note:
            注入发生在 ReactiveRunner 初始化时。
            因此，不要在节点的 __init__ 中访问 self.state_manager，
            它那时可能还是 None。如需初始化时读取状态，请在 setup() 或 initialise() 中进行。
        """
        self.state_manager = state_manager

    def initialise(self) -> None:
        """
        [生命周期] 启动任务
        
        Note:
            每次节点被重新 tick 时都会调用此方法（如果上次不是 RUNNING）。
            无论上次是 SUCCESS 还是 FAILURE，都会重新创建任务。
        """

        if self.async_task and not self.async_task.done():
            self.async_task.cancel()
        
        try:
            loop = asyncio.get_running_loop()
            self.async_task = loop.create_task(self.update_async())
            
            # 关键：任务结束时（无论成功失败），按一下闹钟
            if self._wake_callback:
                self.async_task.add_done_callback(
                    lambda _: self._wake_callback() if self._wake_callback else None
                )
                
        except RuntimeError:
            self.feedback_message = "❌ No active asyncio event loop found."
            self.async_task = None

    def update(self) -> Status:
        """
        [生命周期] 检查状态
        """
        # 1. 任务启动失败
        if self.async_task is None:
            return Status.FAILURE

        # 2. 任务运行中
        if not self.async_task.done():
            return Status.RUNNING

        # 3. 任务结束
        try:
            status = self.async_task.result()
            if not isinstance(status, Status):
                self.feedback_message = f"Invalid return type: {type(status)}"
                return Status.FAILURE
            return status

        except asyncio.CancelledError:
            return Status.INVALID

    def terminate(self, new_status: Status) -> None:
        """
        [生命周期] 终止/中断
        """
        if self.async_task and not self.async_task.done():
            self.async_task.cancel()
        self.async_task = None

    async def update_async(self) -> Status:
        raise NotImplementedError("AsyncBehaviour subclass must implement update_async()")