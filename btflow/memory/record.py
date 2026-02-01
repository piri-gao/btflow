from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class MemoryRecord:
    id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=now_utc)
    embedding: Optional[List[float]] = None
