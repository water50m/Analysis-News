"""Event-driven tracker for the fundamental international-stock watchlist.

The script records daily market snapshots and produces a compact report.  It is a
research tool: it deliberately has no broker integration and emits WATCH /
CAUTION states rather than buy or sell instructions.

Run:
    py -3.11 event_tracker.py --snapshot
    py -3.11 event_tracker.py --report
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from forecasting_store import init_forecasting_db, save_snapshot


ROOT = Path(__file__).resolve().parent
WATCHLIST_PATH = ROOT / "fundamental_watchlist.json"
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
SNAPSHOTS_PATH = DATA_DIR / "fundamental_watchlist_snapshots.csv"
REPORT_PATH = REPORTS_DIR / "fundamental_watchlist_latest.md"

# Macro proxies are intentionally simple and liquid.  Each must be interpreted
# with the event notes in the watchlist, not used in isolation.
MACRO_TICKERS = {
    "gold": "GC=F",
    "oil": "CL=F",
    "copper": "HG=F",
    "dollar": "DX-Y.NYB",
    "ten_year_yield": "^TNX",
    "vix": "^VIX",
    "financials_sector": "XLF",
    "semiconductors_sector": "SOXX",
    "industrials_sector": "XLI",
}

MACRO_LABELS = {
    "gold": "Gold",
    "oil": "Oil",
    "copper": "Copper",
    "dollar": "Dollar",
    "ten_year_yield": "10Y yield",
    "vix": "VIX",
    "financials_sector": "Financials ETF",
    "semiconductors_sector": "Semis ETF",
    "industrials_sector": "Industrials ETF",
}


def load_watchlist(path: Path = WATCHLIST_PATH) -> dict:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _rsi(close: pd.Series, period: int = 14) -> float | None:
    delta = close.diff()
    gains = delta.clip(lower=0).rolling(period).mean()
    losses = -delta.clip(upper=0).rolling(period).mean()
    if len(close) < period + 1 or losses.iloc[-1] == 0:
        return None
    relative_strength = gains.iloc[-1] / losses.iloc[-1]
    return round(100 - (100 / (1 + relative_strength)), 2)


def _last_metrics(frame: pd.DataFrame) -> dict:
    frame = frame.dropna(subset=["Close"]).copy()
    if len(frame) < 21:
        raise ValueError("not enough daily history")

    close = frame["Close"]
    last_close = float(close.iloc[-1])
    previous_close = float(close.iloc[-2])
    sma20 = float(close.tail(20).mean())
    return_5d = ((last_close / float(close.iloc[-6])) - 1) * 100 if len(close) >= 6 else 0.0
    return_20d = ((last_close / float(close.iloc[-21])) - 1) * 100
    volume_ratio = None
    if "Volume" in frame and len(frame) >= 21 and frame["Volume"].tail(20).mean() > 0:
        volume_ratio = float(frame["Volume"].iloc[-1] / frame["Volume"].tail(20).mean())

    return {
        "close": round(last_close, 4),
        "daily_return_pct": round(((last_close / previous_close) - 1) * 100, 2),
        "return_5d_pct": round(return_5d, 2),
        "return_20d_pct": round(return_20d, 2),
        "above_sma20": last_close > sma20,
        "rsi14": _rsi(close),
        "volume_ratio_20d": round(volume_ratio, 2) if volume_ratio is not None else None,
    }


def _download_metrics(tickers: list[str]) -> dict[str, dict]:
    data = yf.download(
        tickers=tickers,
        period="6mo",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
    )
    metrics: dict[str, dict] = {}
    for ticker in tickers:
        try:
            frame = data[ticker] if len(tickers) > 1 else data
            metrics[ticker] = _last_metrics(frame)
        except (KeyError, ValueError, IndexError) as exc:
            metrics[ticker] = {"error": str(exc)}
    return metrics


def score_theme(theme: str, stock: dict, macro: dict[str, dict]) -> tuple[int, str]:
    """Return a transparent, non-trading evidence score in the range -3..+3."""
    if "error" in stock:
        return 0, "DATA ERROR"

    score = 0
    reasons: list[str] = []
    if stock["above_sma20"]:
        score += 1
        reasons.append("price above 20-day average")
    else:
        score -= 1
        reasons.append("price below 20-day average")

    def positive(symbol: str) -> bool:
        return macro.get(symbol, {}).get("return_5d_pct", 0) > 0

    if theme == "gold":
        if positive("gold"):
            score += 1
            reasons.append("gold rising")
        if macro.get("dollar", {}).get("return_5d_pct", 0) < 0:
            score += 1
            reasons.append("dollar easing")
        if macro.get("ten_year_yield", {}).get("return_5d_pct", 0) > 0:
            score -= 1
            reasons.append("10-year yield rising")
    elif theme == "energy":
        if positive("oil"):
            score += 1
            reasons.append("oil rising")
        if macro.get("dollar", {}).get("return_5d_pct", 0) > 0:
            score -= 1
            reasons.append("stronger dollar pressures commodities")
    elif theme == "metals":
        if positive("copper"):
            score += 1
            reasons.append("copper rising")
        if macro.get("dollar", {}).get("return_5d_pct", 0) > 0:
            score -= 1
            reasons.append("stronger dollar pressures metals")
    elif theme == "financials":
        if positive("financials_sector"):
            score += 1
            reasons.append("financial-sector ETF rising")
        if macro.get("vix", {}).get("return_5d_pct", 0) > 10:
            score -= 1
            reasons.append("volatility rising sharply")
    elif theme == "semiconductors":
        if positive("semiconductors_sector"):
            score += 1
            reasons.append("semiconductor-sector ETF rising")
        if macro.get("vix", {}).get("return_5d_pct", 0) > 10:
            score -= 1
            reasons.append("volatility rising sharply")
    elif theme == "industrials":
        if positive("industrials_sector"):
            score += 1
            reasons.append("industrials-sector ETF rising")
        if positive("copper"):
            score += 1
            reasons.append("copper rising")

    score = max(-3, min(3, score))
    rsi = stock.get("rsi14")
    if score >= 2 and rsi is not None and rsi >= 75:
        # A strong trend can still be a poor short-term entry after an extended
        # move. Keep the evidence score, but make the condition visible.
        state = "EXTENDED POSITIVE — WAIT FOR CONFIRMATION"
    elif score >= 2:
        state = "WATCH POSITIVE"
    elif score <= -2:
        state = "CAUTION"
    else:
        state = "MIXED"
    return score, f"{state}: " + "; ".join(reasons)


def build_snapshot(watchlist: dict | None = None) -> pd.DataFrame:
    watchlist = watchlist or load_watchlist()
    entries = watchlist["universe"]
    stock_metrics = _download_metrics([entry["ticker"] for entry in entries])
    macro_metrics = _download_metrics(list(MACRO_TICKERS.values()))
    macro_by_name = {name: macro_metrics[ticker] for name, ticker in MACRO_TICKERS.items()}

    rows = []
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for entry in entries:
        stock = stock_metrics[entry["ticker"]]
        score, state = score_theme(entry["theme"], stock, macro_by_name)
        rows.append({
            "timestamp_utc": timestamp,
            "ticker": entry["ticker"],
            "company": entry["company"],
            "theme": entry["theme"],
            "signal_score": score,
            "state": state,
            **stock,
        })
    return pd.DataFrame(rows), macro_by_name


def append_snapshot(snapshot: pd.DataFrame, path: Path = SNAPSHOTS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot.to_csv(path, mode="a", index=False, header=not path.exists())


def persist_snapshots_to_db(snapshot: pd.DataFrame, macro: dict[str, dict]) -> bool:
    """Persist the raw evidence in Postgres when it is configured.

    CSV remains a convenient local export, but the database is the source for
    forecast accuracy and error analysis over many months.
    """
    if not init_forecasting_db():
        print("⚠️ Forecast DB unavailable; kept the local CSV snapshot only")
        return False

    saved = 0
    for _, row in snapshot.iterrows():
        metrics = row.drop(labels=["timestamp_utc", "ticker", "company", "theme", "signal_score", "state"]).to_dict()
        captured_at = datetime.fromisoformat(row["timestamp_utc"])
        if save_snapshot(
            captured_at=captured_at,
            ticker=row["ticker"],
            theme=row["theme"],
            signal_score=int(row["signal_score"]),
            state=row["state"],
            metrics=metrics,
            macro_metrics=macro,
        ):
            saved += 1
    print(f"Forecast DB: saved {saved}/{len(snapshot)} snapshots")
    return saved == len(snapshot)


def render_report(snapshot: pd.DataFrame, macro: dict[str, dict], watchlist: dict) -> str:
    lines = [
        "# Fundamental Watchlist — latest snapshot",
        "",
        "> Research-only dashboard. `WATCH POSITIVE` and `CAUTION` are evidence states, not buy/sell recommendations.",
        "",
        "## Macro proxies (5-day move)",
        "",
        "| " + " | ".join(MACRO_LABELS[name] for name in MACRO_TICKERS) + " |",
        "|" + "|".join("---:" for _ in MACRO_TICKERS) + "|",
        "| " + " | ".join(
            f"{macro.get(name, {}).get('return_5d_pct', 'N/A')}%"
            for name in MACRO_TICKERS
        ) + " |",
        "",
        "## Watchlist evidence",
        "",
        "| Ticker | Theme | Close | 5D | 20D | RSI14 | Score | State |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for _, row in snapshot.iterrows():
        lines.append(
            f"| {row['ticker']} | {row['theme']} | {row.get('close', 'N/A')} | "
            f"{row.get('return_5d_pct', 'N/A')}% | {row.get('return_20d_pct', 'N/A')}% | "
            f"{row.get('rsi14', 'N/A')} | {row['signal_score']} | {row['state']} |"
        )

    lines.extend(["", "## Next checks", ""])
    for entry in watchlist["universe"]:
        lines.append(f"- **{entry['ticker']}** — catalysts: {', '.join(entry['catalysts'])}. Risks: {', '.join(entry['risks'])}.")
    return "\n".join(lines) + "\n"


def run(snapshot_only: bool = False) -> pd.DataFrame:
    watchlist = load_watchlist()
    snapshot, macro = build_snapshot(watchlist)
    append_snapshot(snapshot)
    persist_snapshots_to_db(snapshot, macro)
    if not snapshot_only:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(render_report(snapshot, macro, watchlist), encoding="utf-8")
        print(f"Report written to {REPORT_PATH}")
    print(snapshot[["ticker", "signal_score", "state"]].to_string(index=False))
    return snapshot


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Track the fundamental event watchlist.")
    parser.add_argument("--snapshot", action="store_true", help="append data without writing a Markdown report")
    args = parser.parse_args()
    run(snapshot_only=args.snapshot)
