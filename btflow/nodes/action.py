from btflow.core import AsyncBehaviour
import asyncio
from py_trees.behaviour import Behaviour
from py_trees.common import Status

class Wait(AsyncBehaviour):
    def __init__(self, name: str, duration: float = 1.0):
        super().__init__(name=name)
        self.duration = float(duration)  # Ensure float even if string is passed

    async def update_async(self) -> Status:
        print(f"⏳ [Wait] {self.name}: Waiting {self.duration}s...")
        await asyncio.sleep(self.duration)
        return Status.SUCCESS
