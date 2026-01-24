import unittest

from btflow.memory import InMemoryHistory, WindowBufferMemory
from btflow.messages import human, ai


class TestInMemoryHistory(unittest.TestCase):
    def test_add_and_search(self):
        mem = InMemoryHistory()
        mem.add([human("hi"), ai("hello")])
        results = mem.search("hello", k=5)
        self.assertTrue(any("hello" in m.content for m in results))

    def test_search_fallback_recent(self):
        mem = InMemoryHistory()
        mem.add([human("a"), ai("b"), human("c")])
        results = mem.search("zzz", k=2)
        self.assertEqual([m.content for m in results], ["b", "c"])


class TestWindowBufferMemory(unittest.TestCase):
    def test_window_limit(self):
        mem = WindowBufferMemory(max_size=2)
        mem.add([human("1"), ai("2"), human("3")])
        results = mem.search("", k=10)
        self.assertEqual([m.content for m in results], ["2", "3"])


if __name__ == "__main__":
    unittest.main()
