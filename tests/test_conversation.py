import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conversation import Conversation, ConversationError, Message  # noqa: E402


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "history.json"

    def tearDown(self):
        self.tmp.cleanup()

    def fill(self, turns=3):
        conversation = Conversation()
        for index in range(turns):
            conversation.add_user(f"вопрос {index}")
            conversation.add_assistant(f"ответ {index}", mode="normal", usage={"input": 1})
        return conversation

    def test_empty(self):
        conversation = Conversation()
        self.assertEqual(len(conversation), 0)
        self.assertEqual(conversation.turns, 0)
        self.assertEqual(conversation.api_messages(), [])

    def test_add_messages(self):
        conversation = self.fill(2)
        self.assertEqual(len(conversation), 4)
        self.assertEqual(conversation.turns, 2)
        self.assertEqual(conversation.messages[0].role, "user")
        self.assertEqual(conversation.messages[1].role, "assistant")

    def test_empty_user_rejected(self):
        with self.assertRaises(ValueError):
            Conversation().add_user("   ")

    def test_api_messages_have_only_roles_and_text(self):
        conversation = self.fill(1)
        self.assertEqual(
            conversation.api_messages(),
            [
                {"role": "user", "content": "вопрос 0"},
                {"role": "assistant", "content": "ответ 0"},
            ],
        )

    def test_api_messages_limit_keeps_pairs(self):
        conversation = self.fill(5)
        messages = conversation.api_messages(4)
        self.assertEqual(len(messages), 4)
        self.assertEqual(messages[0]["content"], "вопрос 3")
        self.assertEqual(messages[-1]["content"], "ответ 4")
        self.assertEqual(messages[0]["role"], "user")

    def test_trim_mutates(self):
        conversation = self.fill(5)
        dropped = conversation.trim(4)
        self.assertEqual(dropped, 6)
        self.assertEqual(len(conversation), 4)
        self.assertEqual(conversation.messages[0].text, "вопрос 3")

    def test_save_and_load(self):
        conversation = self.fill(2)
        conversation.save(self.path)
        loaded = Conversation.load(self.path)
        self.assertEqual(len(loaded), 4)
        self.assertEqual(loaded.messages[0].text, "вопрос 0")
        self.assertEqual(loaded.messages[1].usage, {"input": 1})

    def test_load_missing_file(self):
        self.assertEqual(len(Conversation.load(self.path)), 0)

    def test_load_malformed_file(self):
        self.path.write_text("не json", encoding="utf-8")
        with self.assertRaises(ConversationError):
            Conversation.load(self.path)

    def test_load_skips_invalid_messages(self):
        self.path.write_text(
            json.dumps(
                {
                    "messages": [
                        {"role": "user", "text": "ок"},
                        {"role": "unknown", "text": "плохо"},
                        {"role": "assistant"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        conversation = Conversation.load(self.path)
        self.assertEqual(len(conversation), 1)
        self.assertEqual(conversation.messages[0].text, "ок")

    def test_clear_and_save_empty(self):
        conversation = self.fill(1)
        conversation.clear()
        conversation.save(self.path)
        self.assertEqual(len(Conversation.load(self.path)), 0)

    def test_export_text(self):
        conversation = self.fill(1)
        text = conversation.export_text()
        self.assertIn("Вы: вопрос 0", text)
        self.assertIn("Ассистент: ответ 0", text)

    def test_message_roundtrip(self):
        message = Message(role="assistant", text="ответ", mode="thinking", thinking="думал")
        restored = Message.from_dict(message.to_dict())
        self.assertEqual(restored.text, "ответ")
        self.assertEqual(restored.thinking, "думал")


if __name__ == "__main__":
    unittest.main()
