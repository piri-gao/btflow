import os
import sys

# Ensure repo root is on sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from btflow.memory import Memory, SearchOptions


def test_memory_keyword_search():
    mem = Memory()
    mem.add("Python is great")
    mem.add("I like pizza")

    results = mem.search("python", options=SearchOptions(k=1, mode="keyword"))
    assert results
    assert "Python" in results[0].text


def test_memory_persistence(tmp_path):
    path = tmp_path / "mem.json"
    mem = Memory(persist_path=str(path))
    mem.add("alpha")
    mem.add("beta")

    mem2 = Memory(persist_path=str(path))
    assert len(mem2) == 2
    results = mem2.search("alpha", options=SearchOptions(k=1, mode="keyword"))
    assert results
    assert results[0].text == "alpha"
