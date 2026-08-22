"""Transparent entry-readiness checks shared by the dashboard and backtest.

The checks are evidence filters, not automated investment advice.  A historical
"success" means the price was at least 3% higher after 20 trading sessions.
"""

from __future__ import annotations


def _move(macro: dict, key: str) -> float:
    try:
        return float(macro.get(key, {}).get("return_5d_pct", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def macro_supports_theme(theme: str, macro: dict) -> bool:
    """Require the relevant liquid macro proxy not to oppose the thesis."""
    if theme == "gold":
        return _move(macro, "gold") > 0 and _move(macro, "dollar") <= 0
    if theme == "energy":
        return _move(macro, "oil") > 0 and _move(macro, "dollar") <= 0
    if theme == "metals":
        return _move(macro, "copper") > 0 and _move(macro, "dollar") <= 0
    if theme == "financials":
        return _move(macro, "financials_sector") > 0 and _move(macro, "vix") < 10
    if theme == "semiconductors":
        return _move(macro, "semiconductors_sector") > 0 and _move(macro, "vix") < 10
    if theme == "industrials":
        return _move(macro, "industrials_sector") > 0 and _move(macro, "copper") >= 0
    return False


def evaluate_checklist(theme: str, metrics: dict, macro: dict) -> dict:
    """Evaluate five observable checks; catalyst/news remains intentionally separate."""
    volume_ratio = metrics.get("volume_ratio_20d")
    rsi = metrics.get("rsi14")
    checks = [
        {"key": "trend", "label": "ราคาเหนือ SMA20", "passed": bool(metrics.get("above_sma20"))},
        {"key": "momentum", "label": "โมเมนตัม 5 วันบวก", "passed": (metrics.get("return_5d_pct") or 0) > 0},
        {"key": "volume", "label": "Volume ≥ 1.2× ค่าเฉลี่ย", "passed": volume_ratio is not None and volume_ratio >= 1.2},
        {"key": "rsi", "label": "RSI อยู่ในช่วง 50–72", "passed": rsi is not None and 50 <= rsi <= 72},
        {"key": "macro", "label": "Macro สนับสนุนธีม", "passed": macro_supports_theme(theme, macro)},
    ]
    passed = sum(check["passed"] for check in checks)
    extended = rsi is not None and rsi >= 75
    if extended and passed >= 4:
        status = "EXTENDED"
    elif passed == len(checks):
        status = "ENTRY SETUP READY"
    elif passed >= 3:
        status = "WATCH"
    else:
        status = "WAIT"
    return {"checks": checks, "passed": passed, "total": len(checks), "status": status}
