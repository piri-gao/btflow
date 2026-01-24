import unittest

from btflow.messages import Message, system, human, ai, tool


class TestMessages(unittest.TestCase):
    def test_message_to_dict(self):
        msg = Message(role="user", content="hi", name="u1", tool="t1", metadata={"k": "v"})
        data = msg.to_dict()
        self.assertEqual(data["role"], "user")
        self.assertEqual(data["content"], "hi")
        self.assertEqual(data["name"], "u1")
        self.assertEqual(data["tool"], "t1")
        self.assertEqual(data["metadata"], {"k": "v"})

    def test_factories(self):
        self.assertEqual(system("s").role, "system")
        self.assertEqual(human("h").role, "user")
        self.assertEqual(ai("a").role, "assistant")
        self.assertEqual(tool("t").role, "tool")


if __name__ == "__main__":
    unittest.main()
