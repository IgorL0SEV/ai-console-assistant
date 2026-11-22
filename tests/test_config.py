import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import ConfigError, load_settings, require_key  # noqa: E402


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env_file = self.dir / "missing.env"

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, **env):
        with patch.dict(os.environ, env, clear=True):
            return load_settings(env_file=self.env_file)

    def test_defaults_are_proxyapi(self):
        settings = self.load()
        self.assertEqual(settings.provider, "proxyapi")
        self.assertEqual(settings.normal_model, "openai/gpt-5-mini")
        self.assertEqual(settings.thinking_model, "anthropic/claude-sonnet-4-5")
        self.assertEqual(settings.default_mode, "thinking")
        self.assertEqual(settings.reasoning_budget, 1500)
        self.assertEqual(settings.max_tokens, 4096)
        self.assertEqual(settings.api_key, "")

    def test_provider_override(self):
        settings = self.load()
        with patch.dict(os.environ, {}, clear=True):
            settings = load_settings(env_file=self.env_file, provider_override="anthropic")
        self.assertEqual(settings.provider, "anthropic")
        self.assertEqual(settings.key_env, "ANTHROPIC_API_KEY")
        self.assertEqual(settings.normal_model, "claude-haiku-4-5")
        self.assertEqual(settings.anthropic_base_url, "https://api.anthropic.com")

    def test_key_and_models_from_env(self):
        settings = self.load(
            LLM_PROVIDER="openai",
            OPENAI_API_KEY="sk-test",
            NORMAL_MODEL="gpt-custom",
            THINKING_MODEL="gpt-thinking",
            DEFAULT_MODE="normal",
            REASONING_BUDGET="1200",
            MAX_TOKENS="3000",
            NORMAL_MAX_TOKENS="500",
            NORMAL_REASONING_EFFORT="high",
        )
        self.assertEqual(settings.provider, "openai")
        self.assertEqual(settings.api_key, "sk-test")
        self.assertEqual(settings.normal_model, "gpt-custom")
        self.assertEqual(settings.thinking_model, "gpt-thinking")
        self.assertEqual(settings.default_mode, "normal")
        self.assertEqual(settings.reasoning_budget, 1200)
        self.assertEqual(settings.max_tokens, 3000)
        self.assertEqual(settings.normal_max_tokens, 500)
        self.assertEqual(settings.normal_reasoning_effort, "high")

    def test_placeholder_key_is_empty(self):
        settings = self.load(PROXYAPI_KEY="sk-ВАШ_КЛЮЧ_PROXYAPI")
        self.assertEqual(settings.api_key, "")

    def test_empty_models_use_preset(self):
        settings = self.load(LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="sk-ant")
        self.assertEqual(settings.normal_model, "claude-haiku-4-5")
        self.assertEqual(settings.thinking_model, "claude-sonnet-4-5")

    def test_explicit_model_overrides_preset(self):
        settings = self.load(
            LLM_PROVIDER="anthropic",
            ANTHROPIC_API_KEY="sk-ant",
            THINKING_MODEL="claude-custom",
        )
        self.assertEqual(settings.thinking_model, "claude-custom")
        self.assertEqual(settings.normal_model, "claude-haiku-4-5")

    def test_provider_alias(self):
        self.assertEqual(self.load(LLM_PROVIDER="proxy").provider, "proxyapi")

    def test_invalid_provider(self):
        with self.assertRaises(ConfigError):
            self.load(LLM_PROVIDER="unknown")

    def test_invalid_mode(self):
        with self.assertRaises(ConfigError):
            self.load(DEFAULT_MODE="fast")

    def test_budget_must_be_at_least_1024(self):
        with self.assertRaises(ConfigError):
            self.load(REASONING_BUDGET="500")

    def test_max_tokens_must_exceed_budget(self):
        with self.assertRaises(ConfigError):
            self.load(MAX_TOKENS="1500", REASONING_BUDGET="1500")

    def test_invalid_effort(self):
        with self.assertRaises(ConfigError):
            self.load(NORMAL_REASONING_EFFORT="turbo")

    def test_history_minimum(self):
        with self.assertRaises(ConfigError):
            self.load(MAX_HISTORY_MESSAGES="1")

    def test_env_file_is_read(self):
        env_file = self.dir / "test.env"
        env_file.write_text(
            "LLM_PROVIDER=openrouter\nOPENROUTER_API_KEY=sk-or-test\nNORMAL_MODEL=custom/model\n",
            encoding="utf-8",
        )
        with patch.dict(os.environ, {}, clear=True):
            settings = load_settings(env_file=env_file)
        self.assertEqual(settings.provider, "openrouter")
        self.assertEqual(settings.api_key, "sk-or-test")
        self.assertEqual(settings.normal_model, "custom/model")

    def test_require_key(self):
        settings = self.load()
        with self.assertRaises(ConfigError):
            require_key(settings)
        settings = self.load(PROXYAPI_KEY="sk-test")
        self.assertEqual(require_key(settings), "sk-test")

    def test_model_for_mode(self):
        settings = self.load()
        self.assertEqual(settings.model_for("normal"), "openai/gpt-5-mini")
        self.assertEqual(settings.model_for("thinking"), "anthropic/claude-sonnet-4-5")


if __name__ == "__main__":
    unittest.main()
