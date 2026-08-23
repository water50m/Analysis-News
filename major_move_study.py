"""Study whether large 20-session advances had complete setups beforehand.

This is a descriptive historical study, not a predictive model. It compares
the five observable checklist checks at the *start* of a +10% forward move
against all other eligible daily observations across the 20-stock universe.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from checklist_backtest import HORIZON_DAYS, LOOKBACK_YEARS, _frames, _macro_metrics, _macro_on_day, _stock_metrics
from event_tracker import MACRO_TICKERS, load_watchlist
from signal_checklist import evaluate_checklist


MAJOR_MOVE_PCT = 10.0
REPORT_PATH = Path(__file__).resolve().parent / "reports" / "major_move_study.json"


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator * 100, 1) if denominator else None


def run_study() -> dict:
    universe = load_watchlist()["universe"]
    tickers = [entry["ticker"] for entry in universe]
    frames = _frames(tickers + list(MACRO_TICKERS.values()))
    if not any(ticker in frames and not frames[ticker].empty for ticker in tickers):
        raise RuntimeError("Historical market data is unavailable; study was not calculated.")
    macro = _macro_metrics(frames)
    event_checks, baseline_checks = Counter(), Counter()
    events, baseline = [], 0
    per_ticker = []

    for entry in universe:
        frame = frames.get(entry["ticker"])
        if frame is None or len(frame) <= HORIZON_DAYS + 21:
            continue
        indicators = _stock_metrics(frame)
        ticker_events = []
        previous_was_major = False
        for position in range(21, len(indicators) - HORIZON_DAYS):
            row = indicators.iloc[position]
            if row.isna().any():
                continue
            setup = evaluate_checklist(
                entry["theme"], row.to_dict(), _macro_on_day(macro, indicators.index[position])
            )
            baseline += 1
            baseline_checks.update(check["key"] for check in setup["checks"] if check["passed"])
            forward_return = (float(frame["Close"].iloc[position + HORIZON_DAYS]) / float(row["close"]) - 1) * 100
            is_major = forward_return >= MAJOR_MOVE_PCT

            # One row at the beginning of each consecutive qualifying window
            # avoids counting the same multi-week advance many times.
            if is_major and not previous_was_major:
                record = {
                    "ticker": entry["ticker"],
                    "date": str(indicators.index[position].date()),
                    "forward_return_pct": round(forward_return, 2),
                    "checks_passed": setup["passed"],
                    "checklist_status": setup["status"],
                    "passed_checks": [check["key"] for check in setup["checks"] if check["passed"]],
                    "return_20d_before_pct": round((float(row["close"]) / float(frame["Close"].iloc[position - 20]) - 1) * 100, 2),
                    "rsi14": round(float(row["rsi14"]), 1),
                    "volume_ratio_20d": round(float(row["volume_ratio_20d"]), 2),
                }
                events.append(record)
                ticker_events.append(record)
                event_checks.update(record["passed_checks"])
            previous_was_major = is_major

        per_ticker.append({
            "ticker": entry["ticker"],
            "major_moves": len(ticker_events),
            "complete_setups": sum(event["checks_passed"] == 5 for event in ticker_events),
            "average_checks": round(sum(event["checks_passed"] for event in ticker_events) / len(ticker_events), 2) if ticker_events else None,
        })

    check_comparison = []
    keys = ["trend", "momentum", "volume", "rsi", "macro"]
    for key in keys:
        event_rate = _rate(event_checks[key], len(events))
        baseline_rate = _rate(baseline_checks[key], baseline)
        check_comparison.append({
            "check": key,
            "major_move_rate_pct": event_rate,
            "baseline_rate_pct": baseline_rate,
            "lift_pct_points": round(event_rate - baseline_rate, 1) if event_rate is not None and baseline_rate is not None else None,
        })

    result = {
        "definition": f"Event start where forward {HORIZON_DAYS}-session return is at least {MAJOR_MOVE_PCT}%",
        "lookback_years": LOOKBACK_YEARS,
        "event_count": len(events),
        "complete_checklist_events": sum(event["checks_passed"] == 5 for event in events),
        "incomplete_checklist_events": sum(event["checks_passed"] < 5 for event in events),
        "average_checks_at_event": round(sum(event["checks_passed"] for event in events) / len(events), 2) if events else None,
        "check_comparison": check_comparison,
        "per_ticker": per_ticker,
        "events": events,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    study = run_study()
    print(json.dumps({
        key: study[key] for key in (
            "definition", "event_count", "complete_checklist_events",
            "incomplete_checklist_events", "average_checks_at_event", "check_comparison"
        )
    }, ensure_ascii=False, indent=2))
