import json
import os
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel

class Checkpoint(BaseModel):
    """存档数据结构"""
    thread_id: str
    step: int
    timestamp: str
    state_dump: Dict[str, Any]
    tree_state: Dict[str, str] = {} 

class SimpleCheckpointer:
    def __init__(self, storage_dir: str = ".checkpoints"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)

    def _get_path(self, thread_id: str) -> str:
        return os.path.join(self.storage_dir, f"{thread_id}.jsonl")

    def save(self, thread_id: str, step: int, state_data: Dict[str, Any], tree_state: Dict[str, str]):
        """保存快照 (Data + Tree)"""
        entry = Checkpoint(
            thread_id=thread_id,
            step=step,
            timestamp=datetime.now().isoformat(),
            state_dump=state_data,
            tree_state=tree_state
        )
        path = self._get_path(thread_id)
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")

    def load_latest(self, thread_id: str) -> Optional[Checkpoint]:
        """
        加载最新的 Checkpoint 对象。
        """
        path = self._get_path(thread_id)
        if not os.path.exists(path):
            return None
        
        last_line = None
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last_line = line
        
        if last_line:
            checkpoint = Checkpoint.model_validate_json(last_line)
            print(f"   📂 [Checkpointer] 已恢复存档 (Step {checkpoint.step})")
            return checkpoint
        return None