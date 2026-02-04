from btflow.core.behaviour import AsyncBehaviour
import asyncio
from py_trees.behaviour import Behaviour
from py_trees.common import Status
from btflow.core.logging import logger

class Wait(AsyncBehaviour):
    """Wait for a specified duration, then return SUCCESS."""
    def __init__(self, name: str, duration: float = 1.0):
        super().__init__(name=name)
        self.duration = float(duration)  # Ensure float even if string is passed

    async def update_async(self) -> Status:
        logger.info("⏳ [{}] Waiting {}s...", self.name, self.duration)
        await asyncio.sleep(self.duration)
        return Status.SUCCESS


class SetTask(Behaviour):
    """
    设置当前任务的节点。
    将配置中的 task_content 写入状态中的 task 字段。
    """
    def __init__(self, name: str = "SetTask", task_content: str = ""):
        super().__init__(name=name)
        self.task_content = task_content
        self.state_manager = None

    def update(self) -> Status:
        if self.state_manager:
            logger.info("🎯 [{}] Setting task to: {}", self.name, self.task_content)
            self.state_manager.update({"task": self.task_content})
            return Status.SUCCESS
        return Status.FAILURE
