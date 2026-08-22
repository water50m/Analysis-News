"""Backtest the observable five-check entry setup without look-ahead bias.

Default definition: a completed setup is successful when its closing price is
at least 3% higher after 20 trading sessions. Signals for the same ticker are
spaced 20 sessions apart, so one trend is not counted repeatedly.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from event_tracker import MACRO_TICKERS, load_watchlist
from forecasting_store import init_forecasting_db, save_checklist_backtest_results
from signal_checklist import evaluate_checklist


HORIZON_DAYS = 20
TARGET_RETURN_PCT = 3.0
LOOKBACK_YEARS = 2


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    gains = close.diff().clip(lower=0).rolling(period).mean()
    losses = -close.diff().clip(upper=0).rolling(period).mean()
    return 100 - (100 / (1 + gains / losses.replace(0, float("nan"))))


def _frames(tickers: list[str]) -> dict[str, pd.DataFrame]:
    data = yf.download(
        tickers=tickers, period=f"{LOOKBACK_YEARS}y", interval="1d",
        group_by="ticker", auto_adjust=True, threads=True, progress=False,
    )
    return {ticker: data[ticker].dropna(subset=["Close"]) for ticker in tickers if ticker in data}


def _stock_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    close = frame["Close"]
    volume = frame["Volume"]
    result = pd.DataFrame(index=frame.index)
    result["close"] = close
    result["above_sma20"] = close > close.rolling(20).mean()
    result["return_5d_pct"] = close.pct_change(5) * 100
    result["volume_ratio_20d"] = volume / volume.rolling(20).mean()
    result["rsi14"] = _rsi(close)
    return result


def _macro_metrics(frames: dict[str, pd.DataFrame]) -> dict:
    values = {}
    for name, ticker in MACRO_TICKERS.items():
        frame = frames.get(ticker)
        if frame is None:
            continue
        values[name] = (frame["Close"].pct_change(5) * 100).to_dict()
    return values


def _macro_on_day(metrics: dict, day) -> dict:
    return {
        name: {"return_5d_pct": series.get(day, 0)}
        for name, series in metrics.items()
    }


def run_backtest() -> list[dict]:
    watchlist = load_watchlist()["universe"]
    tickers = [entry["ticker"] for entry in watchlist]
    all_frames = _frames(tickers + list(MACRO_TICKERS.values()))
    macro = _macro_metrics(all_frames)
    run_at = datetime.now(timezone.utc)
    results: list[dict] = []

    for entry in watchlist:
        frame = all_frames.get(entry["ticker"])
        signals: list[tuple[float, float]] = []
        if frame is not None and len(frame) > HORIZON_DAYS + 21:
            indicators = _stock_metrics(frame)
            last_signal_at = -HORIZON_DAYS
            for position in range(21, len(indicators) - HORIZON_DAYS):
                if position - last_signal_at < HORIZON_DAYS:
                    continue
                day = indicators.index[position]
                row = indicators.iloc[position]
                if row.isna().any():
                    continue
                setup = evaluate_checklist(entry["theme"], row.to_dict(), _macro_on_day(macro, day))
                if setup["status"] != "ENTRY SETUP READY":
                    continue
                start = float(row["close"])
                future = frame["Close"].iloc[position + HORIZON_DAYS]
                forward_return = (float(future) / start - 1) * 100
                path = frame["Close"].iloc[position:position + HORIZON_DAYS + 1]
                max_drawdown = (float(path.min()) / start - 1) * 100
                signals.append((forward_return, max_drawdown))
                last_signal_at = position

        outcomes = [item[0] for item in signals]
        drawdowns = [item[1] for item in signals]
        successes = sum(value >= TARGET_RETURN_PCT for value in outcomes)
        results.append({
            "run_at": run_at,
            "ticker": entry["ticker"],
            "signals_count": len(signals),
            "successful_signals": successes,
            "win_rate_pct": round(successes / len(signals) * 100, 2) if signals else None,
            "average_forward_return_pct": round(sum(outcomes) / len(outcomes), 3) if outcomes else None,
            "average_max_drawdown_pct": round(sum(drawdowns) / len(drawdowns), 3) if drawdowns else None,
            "horizon_days": HORIZON_DAYS,
            "target_return_pct": TARGET_RETURN_PCT,
            "lookback_years": LOOKBACK_YEARS,
        })

    if init_forecasting_db():
        save_checklist_backtest_results(results)
    return results


if __name__ == "__main__":
    for result in run_backtest():
        print(result)
