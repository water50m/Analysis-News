import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

import forecasting_store
import services


class TestGeminiRestClient(unittest.TestCase):
    @patch("services.requests.post")
    @patch("services.GEMINI_API_KEY", "test-key")
    @patch("services.GEMINI_MODEL", "gemini-2.5-flash")
    def test_call_gemini_reads_json_candidate(self, mock_post):
        response = MagicMock()
        response.ok = True
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": '{"status": "ok"}'}]}}]
        }
        mock_post.return_value = response

        result = services.call_gemini("test")

        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(mock_post.call_args.kwargs["timeout"], 30)
        self.assertEqual(
            mock_post.call_args.kwargs["json"]["generationConfig"]["responseMimeType"],
            "application/json",
        )

    @patch("services.requests.post")
    @patch("services.GEMINI_API_KEY", "test-key")
    def test_call_gemini_returns_none_for_http_error(self, mock_post):
        response = MagicMock()
        response.ok = False
        response.status_code = 401
        response.text = "bad key"
        response.json.return_value = {"error": {"message": "bad key"}}
        mock_post.return_value = response

        self.assertIsNone(services.call_gemini("test"))


class TestForecastingStoreHelpers(unittest.TestCase):
    def test_json_safe_serializes_database_unfriendly_values(self):
        result = forecasting_store._json_safe({"number": Decimal("1.25")})
        self.assertEqual(result, {"number": "1.25"})

    def test_prediction_input_validation(self):
        with self.assertRaises(ValueError):
            forecasting_store.create_prediction(
                "KGC", 30, "SIDEWAYS", 0.5, "thesis", [], "invalidation", 10.0
            )


if __name__ == "__main__":
    unittest.main()
