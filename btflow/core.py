import asyncio
import traceback
from typing import Callable, Optional
import py_trees
from py_trees.common import Status

class AsyncBehaviour(py_trees.behaviour.Behaviour):
    """
    btflow 核心基类
    """

    def __init__(self, name: str):
        super().__init__(name)
        self.async_task = None 
        # 唤醒回调句柄
        self._wake_callback: Optional[Callable[[], None]] = None

    def bind_wake_up(self, callback: Callable[[], None]):
        """绑定唤醒回调 (通常由 Runner 注入)"""
        self._wake_callback = callback

    def initialise(self) -> None:
        """
        [生命周期] 启动任务
        """
        # 🛡️ 幂等性守卫
        if self.status in (Status.SUCCESS, Status.FAILURE):
            return

        if self.async_task and not self.async_task.done():
            self.async_task.cancel()
        
        try:
            loop = asyncio.get_running_loop()
            self.async_task = loop.create_task(self.update_async())
            
            # 关键：任务结束时（无论成功失败），按一下闹钟
            if self._wake_callback:
                self.async_task.add_done_callback(lambda _: self._wake_callback())
                
        except RuntimeError:
            self.feedback_message = "❌ No active asyncio event loop found."
            self.async_task = None

    def update(self) -> Status:
        """
        [生命周期] 检查状态
        """
        # 🛡️ 状态透传
        if self.status in (Status.SUCCESS, Status.FAILURE) and self.async_task is None:
            return self.status

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
        except Exception as e:
            print(f"\n🔥 [AsyncBehaviour] Node '{self.name}' crashed!")
            traceback.print_exc()
            self.feedback_message = str(e)
            return Status.FAILURE

    def terminate(self, new_status: Status) -> None:
        """
        [生命周期] 终止/中断
        """
        if self.async_task and not self.async_task.done():
            self.async_task.cancel()
        self.async_task = None

    async def update_async(self) -> Status:
        raise NotImplementedError("AsyncBehaviour subclass must implement update_async()")