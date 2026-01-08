from py_trees.behaviour import Behaviour
from py_trees.common import Status
from typing import Callable, Optional

class Log(Behaviour):
    # Class-level callback that can be set by the runner
    _broadcast_callback: Optional[Callable[[str, str], None]] = None
    
    def __init__(self, name: str, message: str = ""):
        super().__init__(name=name)
        self.message = message

    def update(self) -> Status:
        log_msg = f"[{self.name}] {self.message}"
        print(f"📝 [Log] {self.name}: {self.message}")
        
        # Broadcast to frontend if callback is set
        if Log._broadcast_callback:
            Log._broadcast_callback("log", log_msg)
            
        return Status.SUCCESS
