"""คำนวณ Confluence Score แบบ deterministic จากหลายแหล่งข้อมูล (technical, fundamental,
macro, news sentiment) แทนการให้ AI เดา impact_score เองล้วนๆ — ทำให้ผลลัพธ์ตรวจสอบได้
และสม่ำเสมอ ส่วน AI จะใช้คะแนนนี้เป็นหลักฐานในการสรุปทิศทาง/เป้าราคา/จุดตัดขาดทุนต่อ"""


def get_news_sentiment_score(content_data):
    """ดึง ticker_sentiment_score เฉลี่ยจากฟีดข่าว Alpha Vantage (ของเดิมดึงมาแต่ไม่ได้ใช้)
    คืนค่า -2..+2 (สเกลจาก -1..1 ของ Alpha Vantage คูณ 2)"""
    if not content_data:
        return 0

    scores = []
    for news in content_data:
        for topic in news.get("ticker_sentiment", []):
            try:
                scores.append(float(topic["ticker_sentiment_score"]))
            except (KeyError, ValueError, TypeError):
                continue

    if not scores:
        return 0

    avg = sum(scores) / len(scores)
    return max(-2, min(2, round(avg * 2)))


def compute_confluence(technical_score, fundamental_score, macro_score, news_score):
    """รวมคะแนนจาก 4 หมวด (แต่ละหมวด -2..+2) เป็นสัญญาณเดียว

    Returns dict:
        total: ผลรวม (-8..+8)
        direction: UP/DOWN/NEUTRAL ตามเครื่องหมายของ total
        strength: ความแรงของสัญญาณ สเกล 0-10 (สำหรับใช้แทน impact_score เดิม)
        confluence_count: จำนวนหมวดที่เห็นตรงทิศทางเดียวกับ total (ไม่นับหมวดที่เป็น 0)
        breakdown: รายละเอียดคะแนนแต่ละหมวด สำหรับโชว์ใน prompt/log
    """
    components = {
        "Technical": technical_score,
        "Fundamental": fundamental_score,
        "Macro": macro_score,
        "News Sentiment": news_score,
    }

    total = sum(components.values())
    direction = "UP" if total > 0 else "DOWN" if total < 0 else "NEUTRAL"

    sign = 1 if total > 0 else -1 if total < 0 else 0
    confluence_count = sum(1 for v in components.values() if v != 0 and (v > 0) == (sign > 0))

    strength = min(10, round(abs(total) / 8 * 10))

    breakdown = []
    for name, value in components.items():
        tag = "BULLISH" if value > 0 else "BEARISH" if value < 0 else "NEUTRAL"
        breakdown.append(f"{name}: {value:+d} ({tag})")

    return {
        "total": total,
        "direction": direction,
        "strength": strength,
        "confluence_count": confluence_count,
        "breakdown": breakdown,
    }
