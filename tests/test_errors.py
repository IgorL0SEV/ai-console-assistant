import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from errors import LLMError, map_sdk_error, scrub  # noqa: E402


class FakeStatusError(Exception):
    def __init__(self, status, text="error"):
        super().__init__(text)
        self.status_code = status


class APITimeoutError(Exception):
    pass


class APIConnectionError(Exception):
    pass


def mapped(exc):
    return map_sdk_error(exc, provider_title="ProxyAPI", model="test/model")


class MapErrorTests(unittest.TestCase):
    def test_401(self):
        error = mapped(FakeStatusError(401))
        self.assertIsInstance(error, LLMError)
        self.assertEqual(error.kind, "auth")

    def test_402(self):
        error = mapped(FakeStatusError(402))
        self.assertEqual(error.kind, "balance")

    def test_403(self):
        self.assertEqual(mapped(FakeStatusError(403)).kind, "forbidden")

    def test_404_mentions_model(self):
        error = mapped(FakeStatusError(404))
        self.assertEqual(error.kind, "model_not_found")
        self.assertIn("test/model", str(error))

    def test_429_is_retryable(self):
        error = mapped(FakeStatusError(429))
        self.assertEqual(error.kind, "rate_limit")
        self.assertTrue(error.retryable)

    def test_500_is_retryable(self):
        error = mapped(FakeStatusError(502))
        self.assertEqual(error.kind, "server")
        self.assertTrue(error.retryable)

    def test_timeout(self):
        self.assertEqual(mapped(APITimeoutError("timed out")).kind, "timeout")

    def test_connection(self):
        self.assertEqual(mapped(APIConnectionError("connection failed")).kind, "network")

    def test_400_has_details(self):
        error = mapped(FakeStatusError(400, "bad parameter"))
        self.assertEqual(error.kind, "bad_request")
        self.assertIn("bad parameter", str(error))

    def test_scrub_hides_key(self):
        text = scrub("Authorization: Bearer sk-abcdef1234567890 and more")
        self.assertNotIn("abcdef1234567890", text)
        self.assertIn("sk-***", text)

    def test_scrub_limits_length(self):
        self.assertLessEqual(len(scrub("x" * 1000)), 300)


if __name__ == "__main__":
    unittest.main()
