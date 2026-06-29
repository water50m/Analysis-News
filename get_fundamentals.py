import os
import requests
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
FINNHUB_BASE = "https://finnhub.io/api/v1"


def _finnhub_get(path, params=None):
    if not FINNHUB_API_KEY:
        return None
    params = params or {}
    params["token"] = FINNHUB_API_KEY
    try:
        res = requests.get(f"{FINNHUB_BASE}/{path}", params=params, timeout=10)
        return res.json()
    except Exception as e:
        print(f"❌ Finnhub Error ({path}): {e}")
        return None


def get_fundamentals(ticker):
    """ดึงข้อมูลพื้นฐาน: P/E, EPS, Margin, ฯลฯ จาก Finnhub (free tier)"""
    data = _finnhub_get("stock/metric", {"symbol": ticker, "metric": "all"})
    if not data or "metric" not in data:
        return "Fundamentals: N/A"

    m = data["metric"]
    pe = m.get("peNormalizedAnnual") or m.get("peTTM")
    eps = m.get("epsTTM")
    margin = m.get("netProfitMarginTTM")
    de_ratio = m.get("totalDebt/totalEquityAnnual")

    parts = []
    parts.append(f"P/E: {pe:.1f}" if pe else "P/E: N/A")
    parts.append(f"EPS(TTM): {eps:.2f}" if eps else "EPS: N/A")
    parts.append(f"Net Margin: {margin:.1f}%" if margin else "Net Margin: N/A")
    parts.append(f"Debt/Equity: {de_ratio:.2f}" if de_ratio else "Debt/Equity: N/A")

    return " | ".join(parts)


def get_earnings_calendar(ticker):
    """เช็คว่ามีวันประกาศงบใกล้ๆ ไหม (ภายใน 14 วัน)"""
    today = date.today()
    future = today + timedelta(days=14)
    data = _finnhub_get("calendar/earnings", {
        "symbol": ticker,
        "from": today.isoformat(),
        "to": future.isoformat(),
    })
    if not data or not data.get("earningsCalendar"):
        return "No upcoming earnings within 14 days."

    next_event = data["earningsCalendar"][0]
    return f"Earnings Date: {next_event.get('date')} (EPS Estimate: {next_event.get('epsEstimate', 'N/A')})"


def get_insider_sentiment(ticker):
    """สรุปทิศทาง insider buy/sell ล่าสุด"""
    data = _finnhub_get("stock/insider-transactions", {"symbol": ticker})
    if not data or not data.get("data"):
        return "Insider Activity: N/A"

    transactions = data["data"][:10]
    buys = sum(1 for t in transactions if t.get("change", 0) > 0)
    sells = sum(1 for t in transactions if t.get("change", 0) < 0)

    return f"Insider Activity (last {len(transactions)}): {buys} Buy(s), {sells} Sell(s)"


def get_analyst_recommendation(ticker):
    """สรุป consensus ของนักวิเคราะห์ล่าสุด"""
    data = _finnhub_get("stock/recommendation", {"symbol": ticker})
    if not data:
        return "Analyst Rating: N/A"

    latest = data[0]
    return (f"Analyst Rating: Buy={latest.get('buy', 0)} "
            f"Hold={latest.get('hold', 0)} Sell={latest.get('sell', 0)} "
            f"StrongBuy={latest.get('strongBuy', 0)} StrongSell={latest.get('strongSell', 0)}")


def get_fundamental_signal_score(ticker):
    """แปลง insider activity + analyst rating เป็นคะแนนสัญญาณ (-2..+2) สำหรับ confluence scoring"""
    if not ticker or ticker == "GENERAL" or not FINNHUB_API_KEY:
        return 0

    score = 0

    insider_data = _finnhub_get("stock/insider-transactions", {"symbol": ticker})
    if insider_data and insider_data.get("data"):
        transactions = insider_data["data"][:10]
        net = sum(t.get("change", 0) for t in transactions)
        if net > 0:
            score += 1
        elif net < 0:
            score -= 1

    rec_data = _finnhub_get("stock/recommendation", {"symbol": ticker})
    if rec_data:
        latest = rec_data[0]
        bullish = latest.get("buy", 0) + latest.get("strongBuy", 0)
        bearish = latest.get("sell", 0) + latest.get("strongSell", 0)
        if bullish > bearish:
            score += 1
        elif bearish > bullish:
            score -= 1

    return max(-2, min(2, score))


def get_fundamental_context(ticker):
    """รวมทุกข้อมูลพื้นฐานเป็น context string เดียว สำหรับใส่ใน prompt AI"""
    if not ticker or ticker == "GENERAL":
        return "N/A"
    if not FINNHUB_API_KEY:
        return "Fundamentals unavailable (FINNHUB_API_KEY not set)."

    lines = [
        get_fundamentals(ticker),
        get_earnings_calendar(ticker),
        get_insider_sentiment(ticker),
        get_analyst_recommendation(ticker),
    ]
    return "\n".join(lines)
