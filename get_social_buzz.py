"""StockTwits public API (ไม่ต้อง key) — ใช้แทน Twitter ที่ตอนนี้ใช้ไม่ได้ สำหรับวัด
'ความฮือฮา' ของ retail trader ต่อหุ้นตัวหนึ่ง และหาหุ้นที่กำลัง trending ทั้งแพลตฟอร์ม
(หุ้นซิ่งหลายตัวจะโผล่ใน trending ก่อนที่จะอยู่ใน watchlist ของเราด้วยซ้ำ)"""

import requests

STOCKTWITS_BASE = "https://api.stocktwits.com/api/2"
# StockTwits บล็อก default User-Agent ของ requests (Cloudflare bot protection) ต้องปลอมเป็น browser
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def get_trending_symbols():
    """หุ้นที่กำลัง trending ทั้งแพลตฟอร์ม StockTwits ตอนนี้ (ไม่ผูกกับ watchlist ของเรา)"""
    try:
        res = requests.get(f"{STOCKTWITS_BASE}/trending/symbols.json", headers=HEADERS, timeout=10)
        data = res.json()
        return [s["symbol"] for s in data.get("symbols", [])]
    except Exception as e:
        print(f"❌ StockTwits Trending Error: {e}")
        return []


def get_stocktwits_sentiment_score(ticker):
    """นับ sentiment ที่ผู้ใช้ StockTwits ติด tag เอง (Bullish/Bearish) จากข้อความล่าสุด
    คืนคะแนน -2..+2 สำหรับ confluence scoring (ทิศทางจริงจากฝูงชน ไม่ใช่แค่ปริมาณ buzz)"""
    if not ticker or ticker == "GENERAL":
        return 0

    try:
        res = requests.get(f"{STOCKTWITS_BASE}/streams/symbol/{ticker}.json", headers=HEADERS, timeout=10)
        messages = res.json().get("messages", [])
    except Exception as e:
        print(f"❌ StockTwits Sentiment Error ({ticker}): {e}")
        return 0

    bullish, bearish = 0, 0
    for m in messages:
        sentiment = (m.get("entities") or {}).get("sentiment")
        if not sentiment:
            continue
        if sentiment.get("basic") == "Bullish":
            bullish += 1
        elif sentiment.get("basic") == "Bearish":
            bearish += 1

    if bullish == 0 and bearish == 0:
        return 0

    net_ratio = (bullish - bearish) / (bullish + bearish)
    return max(-2, min(2, round(net_ratio * 2)))


def get_social_buzz_context(ticker):
    """string สำหรับใส่ใน prompt AI"""
    if not ticker or ticker == "GENERAL":
        return "Social Buzz: N/A"

    try:
        res = requests.get(f"{STOCKTWITS_BASE}/streams/symbol/{ticker}.json", headers=HEADERS, timeout=10)
        messages = res.json().get("messages", [])
    except Exception:
        return "Social Buzz: N/A"

    sentiments = [(m.get("entities") or {}).get("sentiment") for m in messages]
    bullish = sum(1 for s in sentiments if s and s.get("basic") == "Bullish")
    bearish = sum(1 for s in sentiments if s and s.get("basic") == "Bearish")

    return f"StockTwits (last {len(messages)} msgs): {bullish} Bullish, {bearish} Bearish"
