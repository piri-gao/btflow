import unittest

from btflow.messages import Message, system, human, ai, tool, content_to_text, message_to_text


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

    def test_content_to_text(self):
        content = ["hi", {"text": "there"}]
        self.assertEqual(content_to_text(content), "hi\nthere")

    def test_message_to_text(self):
        msg = Message(role="user", content=[{"text": "hello"}])
        self.assertEqual(message_to_text(msg), "hello")


if __name__ == "__main__":
    unittest.main()
