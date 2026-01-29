import os
import sys

# Ensure repo root is on sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from btflow.core.persistence import Checkpoint


def test_checkpoint_tree_state_not_shared():
    c1 = Checkpoint(thread_id="t1", step=1, timestamp="now", state_dump={})
    c2 = Checkpoint(thread_id="t2", step=2, timestamp="later", state_dump={})

    c1.tree_state["node"] = "RUNNING"

    assert c2.tree_state == {}
