from __future__ import annotations

from pathlib import Path
from typing import List


def load_text(path: str, encoding: str = "utf-8") -> str:
    file_path = Path(path)
    return file_path.read_text(encoding=encoding)


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 0) -> List[str]:
    if chunk_size <= 0:
        return []
    step = max(1, chunk_size - max(0, overlap))
    chunks: List[str] = []
    for start in range(0, len(text), step):
        chunk = text[start : start + chunk_size]
        if chunk:
            chunks.append(chunk)
        if start + chunk_size >= len(text):
            break
    return chunks


__all__ = ["load_text", "chunk_text"]
