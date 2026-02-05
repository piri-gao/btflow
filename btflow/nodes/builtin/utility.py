import asyncio
from typing import Callable, Optional

from py_trees.behaviour import Behaviour
from py_trees.common import Status

from btflow.core.behaviour import AsyncBehaviour
from btflow.core.logging import logger


class Log(Behaviour):
    """Log a message to console (and broadcast to Studio if configured)."""
    _broadcast_callback: Optional[Callable[[str, str], None]] = None

    def __init__(self, name: str, message: str = ""):
        super().__init__(name=name)
        self.message = message

    def update(self) -> Status:
        log_msg = f"[{self.name}] {self.message}"
        logger.info("📝 [Log] {}: {}", self.name, self.message)
        if Log._broadcast_callback:
            Log._broadcast_callback("log", log_msg)
        return Status.SUCCESS


class Wait(AsyncBehaviour):
    """Wait for a specified duration, then return SUCCESS."""
    def __init__(self, name: str, duration: float = 1.0):
        super().__init__(name=name)
        self.duration = float(duration)

    async def update_async(self) -> Status:
        logger.info("⏳ [{}] Waiting {}s...", self.name, self.duration)
        await asyncio.sleep(self.duration)
        return Status.SUCCESS


__all__ = ["Log", "Wait"]
