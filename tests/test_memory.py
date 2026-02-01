import unittest

from btflow.memory import Memory, SearchOptions


class TestMemory(unittest.TestCase):
    def test_add_and_search(self):
        mem = Memory()
        mem.add("hi")
        mem.add("hello")
        results = mem.search("hello", options=SearchOptions(k=5, mode="keyword"))
        self.assertTrue(any("hello" in r.text for r in results))

    def test_search_fallback_recent(self):
        mem = Memory()
        mem.add("a")
        mem.add("b")
        mem.add("c")
        results = mem.search("zzz", options=SearchOptions(k=2, mode="keyword"))
        self.assertEqual([r.text for r in results], ["b", "c"])


class TestWindowLimit(unittest.TestCase):
    def test_window_limit(self):
        mem = Memory(max_size=2)
        mem.add("1")
        mem.add("2")
        mem.add("3")
        results = mem.search("", options=SearchOptions(k=10))
        self.assertEqual([r.text for r in results], ["2", "3"])


if __name__ == "__main__":
    unittest.main()
