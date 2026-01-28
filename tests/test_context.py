import unittest
from types import SimpleNamespace

from btflow.context import ContextBuilder
from btflow.memory import InMemoryHistory
from btflow.messages import system, human


class TestContextBuilder(unittest.TestCase):
    def test_build_includes_system_tools_memory(self):
        mem = InMemoryHistory()
        mem.add([human("memory hello")])

        builder = ContextBuilder(
            system_prompt="sys",
            tools_desc="tool1",
            memory=mem,
            memory_top_k=1,
            max_messages=10,
        )

        user_msgs = [human("user question")]
        messages = builder.build(user_msgs)

        self.assertEqual(messages[0].role, "system")
        self.assertIn("sys", messages[0].content)
        self.assertEqual(messages[1].role, "system")
        self.assertIn("Available tools", messages[1].content)
        self.assertIn("memory hello", messages[2].content)
        self.assertIn("user question", messages[-1].content)

    def test_max_messages_truncation(self):
        builder = ContextBuilder(max_messages=2)
        messages = builder.build([human("1"), human("2"), human("3")])
        self.assertEqual([m.content for m in messages], ["2", "3"])

    def test_build_accepts_state_object(self):
        builder = ContextBuilder(system_prompt="sys")
        state = SimpleNamespace(messages=[human("hello")])
        messages = builder.build(state)
        self.assertEqual(messages[0].role, "system")
        self.assertIn("hello", messages[-1].content)


if __name__ == "__main__":
    unittest.main()
