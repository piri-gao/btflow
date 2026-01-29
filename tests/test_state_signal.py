import os
import sys
from typing import Optional

# Ensure repo root is on sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pydantic import BaseModel

from btflow.core.state import StateManager


class RequiredState(BaseModel):
    task: str
    optional: Optional[str] = None


def test_state_signal_without_initialize():
    state_manager = StateManager(schema=RequiredState)
    hit = {"count": 0}

    def _listener():
        hit["count"] += 1

    state_manager.subscribe(_listener)
    state_manager.signal()

    assert hit["count"] == 1
