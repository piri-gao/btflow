import json
import os
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel
from btflow.core.logging import logger

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
        使用 seek 倒序读取，O(1) 复杂度，避免大文件的启动瓶颈。
        """
        path = self._get_path(thread_id)
        if not os.path.exists(path):
            return None
        
        # 获取文件大小
        file_size = os.path.getsize(path)
        if file_size == 0:
            return None
        
        # 从文件末尾倒序读取，查找最后一个完整的 JSON 行
        chunk_size = 8192  # 每次读取 8KB
        last_line = None
        
        with open(path, "rb") as f:  # 二进制模式，方便 seek
            # 从末尾开始
            position = file_size
            buffer = b""
            
            while position > 0:
                # 计算本次读取的起始位置和大小
                read_size = min(chunk_size, position)
                position -= read_size
                f.seek(position)
                chunk = f.read(read_size)
                buffer = chunk + buffer
                
                # 查找换行符
                lines = buffer.split(b"\n")
                
                # 如果有超过一行，说明找到了完整的行
                if len(lines) > 1:
                    # 倒序查找第一个非空行
                    for line in reversed(lines):
                        stripped = line.strip()
                        if stripped:
                            last_line = stripped.decode("utf-8")
                            break
                    if last_line:
                        break
                    # 保留第一个不完整的片段继续
                    buffer = lines[0]
            
            # 处理文件开头的情况（没有换行符的单行文件）
            if not last_line and buffer.strip():
                last_line = buffer.strip().decode("utf-8")
        
        if last_line:
            checkpoint = Checkpoint.model_validate_json(last_line)
            logger.debug("   📂 [Checkpointer] 已恢复存档 (Step {})", checkpoint.step)
            return checkpoint
        return None