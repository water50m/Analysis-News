import unittest
from unittest.mock import patch

import line_webhook


class TestLineWebhookCommands(unittest.TestCase):
    @patch("line_webhook.reply")
    def test_test_command_replies_without_external_call(self, mock_reply):
        line_webhook.handle_command("/test", "reply-token")
        mock_reply.assert_called_once()
        self.assertIn("webhook", mock_reply.call_args.args[1])

    @patch("line_webhook.reply")
    @patch("line_webhook.get_latest_watchlist_states")
    def test_watchlist_command_formats_states(self, mock_states, mock_reply):
        mock_states.return_value = [{
            "ticker": "KGC", "theme": "gold", "signal_score": 2,
            "state": "WATCH POSITIVE: gold rising", "captured_at": None,
        }]
        line_webhook.handle_command("/watchlist", "reply-token")
        text = mock_reply.call_args.args[1]
        self.assertIn("KGC", text)
        self.assertIn("WATCH POSITIVE", text)


if __name__ == "__main__":
    unittest.main()
