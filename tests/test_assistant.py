import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import assistant  # noqa: E402
from config import Settings  # noqa: E402
from conversation import Conversation  # noqa: E402
from errors import LLMError  # noqa: E402
from providers import Reply  # noqa: E402


def make_settings(tmp, **overrides):
    values = dict(
        provider="proxyapi",
        provider_title="ProxyAPI",
        provider_description="",
        api_key="sk-test",
        key_env="PROXYAPI_KEY",
        normal_model="openai/gpt-5-mini",
        thinking_model="anthropic/claude-sonnet-4-5",
        default_mode="thinking",
        reasoning_budget=1500,
        max_tokens=4096,
        normal_max_tokens=2048,
        normal_reasoning_effort="medium",
        system_prompt="system",
        timeout=30.0,
        max_retries=0,
        max_history_messages=6,
        history_file=Path(tmp) / "history.json",
        log_file=Path(tmp) / "log.txt",
        data_dir=Path(tmp),
        openai_base_url="https://api.proxyapi.ru/v1",
        anthropic_base_url="https://api.proxyapi.ru",
        project_root=Path(tmp),
    )
    values.update(overrides)
    return Settings(**values)


class FakeProvider:
    def __init__(self, error=None):
        self.error = error
        self.messages = None

    def complete(self, messages, system):
        self.messages = messages
        if self.error:
            raise self.error
        return Reply(
            text="ответ",
            thinking="размышление",
            model="test/model",
            usage={"input": 3, "output": 4},
            latency=0.2,
        )


class SendMessageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = make_settings(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_success_adds_and_saves(self):
        conversation = Conversation()
        provider = FakeProvider()
        reply, dropped = assistant.send_message(
            provider, conversation, self.settings, "thinking", "Привет"
        )
        self.assertEqual(reply.text, "ответ")
        self.assertEqual(dropped, 0)
        self.assertEqual(len(conversation), 2)
        self.assertEqual(conversation.messages[0].text, "Привет")
        self.assertEqual(conversation.messages[1].thinking, "размышление")
        self.assertTrue(self.settings.history_file.exists())
        loaded = Conversation.load(self.settings.history_file)
        self.assertEqual(len(loaded), 2)

    def test_request_contains_history_and_user(self):
        conversation = Conversation()
        conversation.add_user("старое")
        conversation.add_assistant("старый ответ", mode="normal")
        provider = FakeProvider()
        assistant.send_message(provider, conversation, self.settings, "normal", "новое")
        self.assertEqual(provider.messages[-1], {"role": "user", "content": "новое"})
        self.assertEqual(provider.messages[0]["content"], "старое")

    def test_error_does_not_change_history(self):
        conversation = Conversation()
        provider = FakeProvider(error=LLMError("нет связи", kind="network"))
        with self.assertRaises(LLMError):
            assistant.send_message(provider, conversation, self.settings, "normal", "Привет")
        self.assertEqual(len(conversation), 0)
        self.assertFalse(self.settings.history_file.exists())

    def test_history_is_trimmed(self):
        conversation = Conversation()
        for index in range(10):
            conversation.add_user(f"вопрос {index}")
            conversation.add_assistant(f"ответ {index}", mode="normal")
        assistant.send_message(FakeProvider(), conversation, self.settings, "normal", "новое")
        self.assertLessEqual(len(conversation), self.settings.max_history_messages)
        self.assertEqual(conversation.messages[0].role, "user")


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = make_settings(self.tmp.name)
        self.conversation = Conversation()
        self.conversation.add_user("Привет")
        self.conversation.add_assistant("Здравствуйте", mode="normal")

    def tearDown(self):
        self.tmp.cleanup()

    def run_command(self, text):
        with redirect_stdout(io.StringIO()):
            return assistant.handle_command(
                text, self.conversation, self.settings, "normal"
            )

    def test_exit(self):
        self.assertTrue(self.run_command("exit").exit)
        self.assertTrue(self.run_command("/quit").exit)
        self.assertTrue(self.run_command("выход").exit)

    def test_plain_text_is_not_command(self):
        self.assertFalse(self.run_command("привет").handled)

    def test_normal_and_thinking(self):
        self.assertEqual(self.run_command("/normal").mode, "normal")
        self.assertEqual(self.run_command("/thinking").mode, "thinking")

    def test_mode_uses_prompt(self):
        with patch("assistant.choose_mode", return_value="thinking"):
            result = self.run_command("/mode")
        self.assertEqual(result.mode, "thinking")

    def test_clear(self):
        result = self.run_command("/clear")
        self.assertTrue(result.handled)
        self.assertEqual(len(self.conversation), 0)
        self.assertTrue(self.settings.history_file.exists())

    def test_help_history_status(self):
        for command in ("/help", "/history", "/status", "/?"):
            self.assertTrue(self.run_command(command).handled)

    def test_unknown_command(self):
        with redirect_stdout(io.StringIO()):
            result = assistant.handle_command(
                "/unknown", self.conversation, self.settings, "normal"
            )
        self.assertTrue(result.handled)


class ModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = make_settings(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_requested_mode_wins(self):
        self.assertEqual(
            assistant.resolve_mode("normal", self.settings, interactive=True), "normal"
        )

    def test_default_without_interactive(self):
        self.assertEqual(
            assistant.resolve_mode(None, self.settings, interactive=False), "thinking"
        )


class MainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = make_settings(self.tmp.name)

    def tearDown(self):
        assistant.shutdown_logging()
        self.tmp.cleanup()

    def test_demo_returns_zero(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "proxyapi"}, clear=False):
            with patch("assistant.load_settings", return_value=self.settings):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(assistant.main(["--demo"]), 0)

    def test_check_without_key(self):
        settings = make_settings(self.tmp.name, api_key="")
        with patch("assistant.load_settings", return_value=settings):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(assistant.main(["--check"]), 2)

    def test_once_without_key(self):
        settings = make_settings(self.tmp.name, api_key="")
        with patch("assistant.load_settings", return_value=settings):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(assistant.main(["--once", "Привет"]), 2)

    def test_once_with_fake_provider(self):
        with patch("assistant.load_settings", return_value=self.settings):
            with patch("assistant.build_provider", return_value=FakeProvider()):
                with redirect_stdout(io.StringIO()):
                    code = assistant.main(["--once", "Привет", "--no-history"])
        self.assertEqual(code, 0)
        self.assertTrue(self.settings.history_file.exists())


if __name__ == "__main__":
    unittest.main()
