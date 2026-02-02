from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from btflow.memory.record import MemoryRecord


class MemoryStore:
    def add(self, record: MemoryRecord) -> str:
        raise NotImplementedError

    def get(self, record_id: str) -> Optional[MemoryRecord]:
        raise NotImplementedError

    def list(self) -> List[MemoryRecord]:
        raise NotImplementedError

    def delete(self, record_id: str) -> bool:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError


def record_to_dict(record: MemoryRecord) -> Dict[str, object]:
    return {
        "id": record.id,
        "text": record.text,
        "metadata": record.metadata,
        "created_at": record.created_at.isoformat(),
        "embedding": record.embedding,
    }


def record_from_dict(data: Dict[str, object]) -> MemoryRecord:
    from datetime import datetime, timezone

    created_at_raw = data.get("created_at")
    if isinstance(created_at_raw, str):
        try:
            created_at = datetime.fromisoformat(created_at_raw)
        except ValueError:
            created_at = datetime.now(timezone.utc)
    else:
        created_at = datetime.now(timezone.utc)

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    return MemoryRecord(
        id=str(data.get("id")),
        text=str(data.get("text", "")),
        metadata=dict(data.get("metadata") or {}),
        created_at=created_at,
        embedding=data.get("embedding"),
    )


class InMemoryStore(MemoryStore):
    def __init__(self, max_size: Optional[int] = None):
        self.max_size = max_size
        self._records: Dict[str, MemoryRecord] = {}
        self._order: List[str] = []

    def add(self, record: MemoryRecord) -> str:
        self._records[record.id] = record
        self._order.append(record.id)
        if self.max_size is not None and len(self._order) > self.max_size:
            overflow = len(self._order) - self.max_size
            for _ in range(overflow):
                old_id = self._order.pop(0)
                self._records.pop(old_id, None)


        return record.id

    def get(self, record_id: str) -> Optional[MemoryRecord]:
        return self._records.get(record_id)

    def list(self) -> List[MemoryRecord]:
        return [self._records[i] for i in self._order if i in self._records]

    def delete(self, record_id: str) -> bool:
        if record_id not in self._records:
            return False
        self._records.pop(record_id, None)
        self._order = [i for i in self._order if i != record_id]
        return True

    def clear(self) -> None:
        self._records.clear()
        self._order.clear()

    def __len__(self) -> int:
        return len(self._order)


class JsonStore(InMemoryStore):
    def __init__(self, path: str, max_size: Optional[int] = None, autosave: bool = True):
        super().__init__(max_size=max_size)
        self.path = Path(path)
        self.autosave = autosave
        if self.path.exists():
            self.load()

    def add(self, record: MemoryRecord) -> str:
        record_id = super().add(record)
        if self.autosave:
            self.save()
        return record_id

    def delete(self, record_id: str) -> bool:
        removed = super().delete(record_id)
        if removed and self.autosave:
            self.save()
        return removed

    def clear(self) -> None:
        super().clear()
        if self.autosave:
            self.save()

    def save(self) -> None:
        data = {
            "records": [record_to_dict(r) for r in self.list()],
            "order": list(self._order),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self) -> None:
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._records = {}
        self._order = []
        records = data.get("records") or []
        for item in records:
            record = record_from_dict(item)
            self._records[record.id] = record
        order = data.get("order") or []
        if order:
            self._order = [i for i in order if i in self._records]
        else:
            self._order = list(self._records.keys())
        if self.max_size is not None and len(self._order) > self.max_size:
            overflow = len(self._order) - self.max_size
            for _ in range(overflow):
                old_id = self._order.pop(0)
                self._records.pop(old_id, None)

class SQLiteStore(MemoryStore):
    def __init__(self, path: str, max_size: Optional[int] = None):
        self.path = Path(path)
        self.max_size = max_size
        if self.path.parent:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT UNIQUE,
                text TEXT,
                metadata TEXT,
                created_at TEXT,
                embedding TEXT
            )
            """
        )
        self._conn.commit()

    def add(self, record: MemoryRecord) -> str:
        self._conn.execute(
            "INSERT OR REPLACE INTO records (id, text, metadata, created_at, embedding) VALUES (?, ?, ?, ?, ?)",
            (
                record.id,
                record.text,
                json.dumps(record.metadata, ensure_ascii=False),
                record.created_at.isoformat(),
                json.dumps(record.embedding) if record.embedding is not None else None,
            ),
        )
        self._conn.commit()
        if self.max_size is not None:
            self._trim_to_size()
        return record.id

    def get(self, record_id: str) -> Optional[MemoryRecord]:
        cur = self._conn.execute(
            "SELECT id, text, metadata, created_at, embedding FROM records WHERE id = ?",
            (record_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return record_from_dict(
            {
                "id": row[0],
                "text": row[1],
                "metadata": json.loads(row[2] or "{}"),
                "created_at": row[3],
                "embedding": json.loads(row[4]) if row[4] else None,
            }
        )

    def list(self) -> List[MemoryRecord]:
        cur = self._conn.execute(
            "SELECT id, text, metadata, created_at, embedding FROM records ORDER BY seq ASC"
        )
        records: List[MemoryRecord] = []
        for row in cur.fetchall():
            records.append(
                record_from_dict(
                    {
                        "id": row[0],
                        "text": row[1],
                        "metadata": json.loads(row[2] or "{}"),
                        "created_at": row[3],
                        "embedding": json.loads(row[4]) if row[4] else None,
                    }
                )
            )
        return records

    def delete(self, record_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM records WHERE id = ?", (record_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def clear(self) -> None:
        self._conn.execute("DELETE FROM records")
        self._conn.commit()

    def __len__(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM records")
        row = cur.fetchone()
        return int(row[0] or 0)

    def _trim_to_size(self) -> None:
        if self.max_size is None:
            return
        cur = self._conn.execute("SELECT COUNT(*) FROM records")
        count = int(cur.fetchone()[0] or 0)
        overflow = count - self.max_size
        if overflow <= 0:
            return
        self._conn.execute(
            "DELETE FROM records WHERE seq IN (SELECT seq FROM records ORDER BY seq ASC LIMIT ?)",
            (overflow,),
        )
        self._conn.commit()


__all__ = [
    "MemoryStore",
    "InMemoryStore",
    "JsonStore",
    "SQLiteStore",
    "record_to_dict",
    "record_from_dict",
]
