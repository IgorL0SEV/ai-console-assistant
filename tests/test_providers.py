import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import ConfigError, Settings  # noqa: E402
from errors import LLMError  # noqa: E402
from providers import (  # noqa: E402
    AnthropicMessagesProvider,
    OpenAICompatibleProvider,
    build_provider,
)


class FakeStatusError(Exception):
    def __init__(self, status):
        super().__init__("fake error")
        self.status_code = status


class FakeCompletions:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


class FakeOpenAI:
    def __init__(self, response=None, error=None):
        self.completions = FakeCompletions(response, error)
        self.chat = SimpleNamespace(completions=self.completions)


class FakeMessages:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


class FakeAnthropic:
    def __init__(self, response=None, error=None):
        self.messages = FakeMessages(response, error)


def openai_response(text="Привет", reasoning=None):
    message = SimpleNamespace(content=text, reasoning_content=reasoning)
    usage = SimpleNamespace(
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        completion_tokens_details=None,
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def anthropic_response(text="Ответ", thinking=None):
    content = []
    if thinking:
        content.append(SimpleNamespace(type="thinking", thinking=thinking))
    content.append(SimpleNamespace(type="text", text=text))
    usage = SimpleNamespace(
        input_tokens=12,
        output_tokens=20,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return SimpleNamespace(content=content, usage=usage)


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
        max_history_messages=20,
        history_file=Path(tmp) / "history.json",
        log_file=Path(tmp) / "log.txt",
        data_dir=Path(tmp),
        openai_base_url="https://api.proxyapi.ru/v1",
        anthropic_base_url="https://api.proxyapi.ru",
        project_root=Path(tmp),
    )
    values.update(overrides)
    return Settings(**values)


class OpenAITests(unittest.TestCase):
    def make(self, client, **kwargs):
        return OpenAICompatibleProvider(
            title="ProxyAPI",
            api_key="sk-test",
            base_url="https://example.test/v1",
            model="openai/gpt-5-mini",
            mode="normal",
            max_tokens=100,
            timeout=30,
            max_retries=0,
            client=client,
            **kwargs,
        )

    def test_request_shape(self):
        client = FakeOpenAI(openai_response())
        provider = self.make(client)
        reply = provider.complete([{"role": "user", "content": "Привет"}], "system")
        self.assertEqual(reply.text, "Привет")
        self.assertEqual(reply.usage["input"], 10)
        self.assertEqual(client.completions.kwargs["model"], "openai/gpt-5-mini")
        self.assertEqual(client.completions.kwargs["messages"][0]["role"], "system")
        self.assertEqual(client.completions.kwargs["messages"][1]["content"], "Привет")
        self.assertEqual(client.completions.kwargs["max_tokens"], 100)

    def test_max_completion_tokens_parameter(self):
        client = FakeOpenAI(openai_response())
        provider = self.make(client, max_tokens_param="max_completion_tokens")
        provider.complete([], "system")
        self.assertIn("max_completion_tokens", client.completions.kwargs)
        self.assertNotIn("max_tokens", client.completions.kwargs)

    def test_reasoning_effort(self):
        client = FakeOpenAI(openai_response())
        provider = self.make(client, reasoning_style="effort", reasoning_effort="high")
        provider.complete([], "system")
        self.assertEqual(client.completions.kwargs["reasoning_effort"], "high")
        self.assertNotIn("extra_body", client.completions.kwargs)

    def test_openrouter_reasoning(self):
        client = FakeOpenAI(openai_response())
        provider = self.make(client, reasoning_style="openrouter", reasoning_effort="low")
        provider.complete([], "system")
        self.assertEqual(
            client.completions.kwargs["extra_body"],
            {"reasoning": {"effort": "low"}},
        )

    def test_reasoning_content(self):
        client = FakeOpenAI(openai_response(reasoning="думал"))
        reply = self.make(client).complete([], "system")
        self.assertEqual(reply.thinking, "думал")

    def test_empty_response(self):
        client = FakeOpenAI(openai_response(text=""))
        with self.assertRaises(LLMError):
            self.make(client).complete([], "system")

    def test_error_mapping(self):
        client = FakeOpenAI(error=FakeStatusError(401))
        with self.assertRaises(LLMError) as context:
            self.make(client).complete([], "system")
        self.assertEqual(context.exception.kind, "auth")


class AnthropicTests(unittest.TestCase):
    def make(self, client, **kwargs):
        return AnthropicMessagesProvider(
            title="Claude",
            api_key="sk-test",
            base_url="https://example.test",
            model="anthropic/claude-sonnet-4-5",
            mode="thinking",
            max_tokens=4096,
            timeout=30,
            max_retries=0,
            client=client,
            **kwargs,
        )

    def test_thinking_and_text(self):
        client = FakeAnthropic(anthropic_response(text="Ответ", thinking="Размышление"))
        reply = self.make(client, thinking_budget=1500).complete(
            [{"role": "user", "content": "Привет"}], "system"
        )
        self.assertEqual(reply.text, "Ответ")
        self.assertEqual(reply.thinking, "Размышление")
        self.assertEqual(reply.usage["input"], 12)
        self.assertEqual(reply.usage["output"], 20)

    def test_thinking_parameter(self):
        client = FakeAnthropic(anthropic_response())
        self.make(client, thinking_budget=1500).complete([], "system")
        self.assertEqual(
            client.messages.kwargs["thinking"],
            {"type": "enabled", "budget_tokens": 1500},
        )
        self.assertEqual(client.messages.kwargs["max_tokens"], 4096)
        self.assertEqual(client.messages.kwargs["system"], "system")

    def test_normal_mode_has_no_thinking(self):
        client = FakeAnthropic(anthropic_response())
        self.make(client, thinking_budget=None).complete([], "system")
        self.assertNotIn("thinking", client.messages.kwargs)

    def test_text_only(self):
        client = FakeAnthropic(anthropic_response())
        reply = self.make(client).complete([], "system")
        self.assertIsNone(reply.thinking)

    def test_no_text_raises(self):
        client = FakeAnthropic(anthropic_response(text=""))
        with self.assertRaises(LLMError):
            self.make(client).complete([], "system")

    def test_error_mapping(self):
        client = FakeAnthropic(error=FakeStatusError(429))
        with self.assertRaises(LLMError) as context:
            self.make(client).complete([], "system")
        self.assertEqual(context.exception.kind, "rate_limit")


class BuildProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = make_settings(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_key(self):
        settings = make_settings(self.tmp.name, api_key="")
        with self.assertRaises(ConfigError):
            build_provider(settings, "thinking")

    def test_proxyapi_thinking_is_anthropic(self):
        with patch("providers.AnthropicMessagesProvider") as mocked:
            build_provider(self.settings, "thinking")
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs["model"], "anthropic/claude-sonnet-4-5")
        self.assertEqual(kwargs["thinking_budget"], 1500)
        self.assertEqual(kwargs["base_url"], "https://api.proxyapi.ru")

    def test_proxyapi_normal_is_openai(self):
        with patch("providers.OpenAICompatibleProvider") as mocked:
            build_provider(self.settings, "normal")
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs["model"], "openai/gpt-5-mini")
        self.assertEqual(kwargs["base_url"], "https://api.proxyapi.ru/v1")

    def test_anthropic_provider_models(self):
        settings = make_settings(
            self.tmp.name,
            provider="anthropic",
            key_env="ANTHROPIC_API_KEY",
            anthropic_base_url="https://api.anthropic.com",
            normal_model="claude-haiku-4-5",
            thinking_model="claude-sonnet-4-5",
        )
        with patch("providers.AnthropicMessagesProvider") as mocked:
            build_provider(settings, "thinking")
        self.assertEqual(mocked.call_args.kwargs["model"], "claude-sonnet-4-5")
        self.assertEqual(mocked.call_args.kwargs["thinking_budget"], 1500)
        with patch("providers.AnthropicMessagesProvider") as mocked:
            build_provider(settings, "normal")
        self.assertEqual(mocked.call_args.kwargs["model"], "claude-haiku-4-5")
        self.assertIsNone(mocked.call_args.kwargs["thinking_budget"])

    def test_openai_provider_uses_reasoning_effort(self):
        settings = make_settings(
            self.tmp.name,
            provider="openai",
            key_env="OPENAI_API_KEY",
            openai_base_url="https://api.openai.com/v1",
            normal_model="gpt-5-mini",
            thinking_model="gpt-5",
        )
        with patch("providers.OpenAICompatibleProvider") as mocked:
            build_provider(settings, "thinking")
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs["reasoning_style"], "effort")
        self.assertEqual(kwargs["max_tokens_param"], "max_completion_tokens")

    def test_openrouter_provider(self):
        settings = make_settings(
            self.tmp.name,
            provider="openrouter",
            key_env="OPENROUTER_API_KEY",
            openai_base_url="https://openrouter.ai/api/v1",
        )
        with patch("providers.OpenAICompatibleProvider") as mocked:
            build_provider(settings, "thinking")
        self.assertEqual(mocked.call_args.kwargs["reasoning_style"], "openrouter")


if __name__ == "__main__":
    unittest.main()
