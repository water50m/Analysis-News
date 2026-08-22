import unittest

import event_tracker


class TestEventTracker(unittest.TestCase):
    def test_gold_score_rewards_rising_gold_and_easing_dollar(self):
        stock = {"above_sma20": True, "rsi14": 55}
        macro = {
            "gold": {"return_5d_pct": 2.0},
            "dollar": {"return_5d_pct": -1.0},
            "ten_year_yield": {"return_5d_pct": -0.5},
        }
        score, state = event_tracker.score_theme("gold", stock, macro)
        self.assertEqual(score, 3)
        self.assertTrue(state.startswith("WATCH POSITIVE"))

    def test_extended_rsi_is_flagged_even_when_evidence_is_positive(self):
        stock = {"above_sma20": True, "rsi14": 80}
        macro = {
            "gold": {"return_5d_pct": 2.0},
            "dollar": {"return_5d_pct": -1.0},
            "ten_year_yield": {"return_5d_pct": -0.5},
        }
        _, state = event_tracker.score_theme("gold", stock, macro)
        self.assertTrue(state.startswith("EXTENDED POSITIVE"))

    def test_energy_score_flags_falling_oil_and_weak_price(self):
        stock = {"above_sma20": False, "rsi14": 45}
        macro = {"oil": {"return_5d_pct": -3.0}, "dollar": {"return_5d_pct": 1.0}}
        score, state = event_tracker.score_theme("energy", stock, macro)
        self.assertEqual(score, -2)
        self.assertTrue(state.startswith("CAUTION"))

    def test_data_error_is_neutral(self):
        score, state = event_tracker.score_theme("gold", {"error": "missing"}, {})
        self.assertEqual((score, state), (0, "DATA ERROR"))

    def test_financials_score_uses_sector_and_volatility(self):
        stock = {"above_sma20": True, "rsi14": 55}
        macro = {
            "financials_sector": {"return_5d_pct": 2.0},
            "vix": {"return_5d_pct": 0.0},
        }
        score, state = event_tracker.score_theme("financials", stock, macro)
        self.assertEqual(score, 2)
        self.assertTrue(state.startswith("WATCH POSITIVE"))

    def test_watchlist_has_twenty_unique_tickers(self):
        watchlist = event_tracker.load_watchlist()
        tickers = [entry["ticker"] for entry in watchlist["universe"]]
        self.assertEqual(len(tickers), 20)
        self.assertEqual(len(set(tickers)), 20)


if __name__ == "__main__":
    unittest.main()
