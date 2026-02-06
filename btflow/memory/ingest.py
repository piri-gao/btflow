from __future__ import annotations

from pathlib import Path
from typing import List

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

try:
    import docx
except Exception:
    docx = None


def load_text(path: str, encoding: str = "utf-8") -> str:
    file_path = Path(path)
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        if PdfReader is None:
            raise RuntimeError("pypdf not installed. Run: pip install pypdf")
        reader = PdfReader(str(file_path))
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text:
                pages.append(text)
        return "\n".join(pages)

    if suffix == ".docx":
        if docx is None:
            raise RuntimeError("python-docx not installed. Run: pip install python-docx")
        doc = docx.Document(str(file_path))
        return "\n".join(p.text for p in doc.paragraphs if p.text)

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
