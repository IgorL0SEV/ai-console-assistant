import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui import format_usage  # noqa: E402


class UsageFormatTests(unittest.TestCase):
    def test_full_usage(self):
        text = format_usage({"input": 10, "output": 20, "reasoning": 5}, 1.25)
        self.assertIn("вход 10", text)
        self.assertIn("выход 20", text)
        self.assertIn("reasoning 5", text)
        self.assertIn("1.2 с", text)

    def test_empty_usage(self):
        self.assertIn("нет данных", format_usage({}))

    def test_cache_usage(self):
        self.assertIn("кэш 7", format_usage({"input": 1, "cache_read": 7}))


if __name__ == "__main__":
    unittest.main()
