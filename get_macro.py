import os
import requests
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

FRED_API_KEY = os.getenv("FRED_API_KEY")
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Series ที่สนใจ: อัตราดอกเบี้ย Fed, เงินเฟ้อ (CPI), อัตราว่างงาน
FRED_SERIES = {
    "Fed Funds Rate": "FEDFUNDS",
    "CPI (Inflation)": "CPIAUCSL",
    "Unemployment Rate": "UNRATE",
}


def _get_vix_value():
    try:
        df = yf.Ticker("^VIX").history(period="5d")
        return None if df.empty else float(df["Close"].iloc[-1])
    except Exception:
        return None


def get_vix():
    """ดึงดัชนีความกลัวตลาด VIX จาก yfinance (ฟรี)"""
    vix = _get_vix_value()
    if vix is None:
        return "VIX: N/A"
    level = "HIGH FEAR" if vix > 25 else "LOW FEAR" if vix < 15 else "NEUTRAL"
    return f"VIX: {vix:.1f} ({level})"


def get_macro_signal_score():
    """แปลง VIX เป็นคะแนนสัญญาณเชิงปริมาณ (-2..+2) สำหรับ confluence scoring
    VIX ต่ำ (<15) = risk-on/bullish, VIX สูง (>25) = risk-off/bearish"""
    vix = _get_vix_value()
    if vix is None:
        return 0
    if vix < 15:
        return 1
    if vix > 25:
        return -1
    return 0


def _fred_latest(series_id):
    if not FRED_API_KEY:
        return None
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 1,
    }
    try:
        res = requests.get(FRED_BASE, params=params, timeout=10).json()
        obs = res.get("observations", [])
        return obs[0] if obs else None
    except Exception as e:
        print(f"❌ FRED Error ({series_id}): {e}")
        return None


def get_macro_context():
    """รวมข้อมูล Macro (Fed Rate, CPI, Unemployment, VIX) เป็น context string"""
    lines = [get_vix()]

    if not FRED_API_KEY:
        lines.append("Macro data (Fed/CPI/Unemployment) unavailable (FRED_API_KEY not set).")
        return "\n".join(lines)

    for name, series_id in FRED_SERIES.items():
        obs = _fred_latest(series_id)
        if obs:
            lines.append(f"{name}: {obs['value']} (as of {obs['date']})")
        else:
            lines.append(f"{name}: N/A")

    return "\n".join(lines)
