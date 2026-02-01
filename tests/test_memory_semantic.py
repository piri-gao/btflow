import os
import sys

# Ensure repo root is on sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from btflow.memory import Memory, SearchOptions


def test_memory_semantic_search():
    mem = Memory()
    mem.add("hello hello")
    mem.add("pizza is great")

    results = mem.search("hello", options=SearchOptions(k=1, mode="semantic"))
    assert results
    assert "hello" in results[0].text
