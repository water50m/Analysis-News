"""Screener: สแกนหุ้นจาก watchlist_universe.txt หา 'หุ้นซิ่ง' ของวันนี้ (% เปลี่ยนแปลง + volume spike)
ใช้ yfinance batch download เท่านั้น — ไม่มี API key/quota จึงสแกนได้หลายร้อยตัวพร้อมกันโดยไม่เสียค่าใช้จ่าย
ผลลัพธ์ top N จะถูกเขียนทับ target_ticker.txt ให้ get_news.py ไปวิเคราะห์ลึกต่อ (ที่ใช้ quota จำกัด)"""

import yfinance as yf

UNIVERSE_FILE = "watchlist_universe.txt"
TARGET_FILE = "target_ticker.txt"

MIN_PCT_CHANGE = 3.0      # % เปลี่ยนแปลงขั้นต่ำที่ถือว่า "ซิ่ง"
MIN_VOLUME_RATIO = 1.5    # volume วันนี้ต้องสูงกว่าค่าเฉลี่ย 20 วันอย่างน้อยกี่เท่า


def load_universe():
    try:
        with open(UNIVERSE_FILE, "r") as f:
            return [line.strip().upper() for line in f
                    if line.strip() and not line.strip().startswith("#")]
    except FileNotFoundError:
        print(f"❌ ไม่พบไฟล์ {UNIVERSE_FILE}")
        return []


def scan_movers(tickers):
    """สแกนทุก ticker พร้อมกันด้วย yfinance batch download คืน list of dict ที่ผ่านเกณฑ์ 'ซิ่ง'"""
    if not tickers:
        return []

    print(f"🔍 Scanning {len(tickers)} tickers...")
    data = yf.download(
        tickers=" ".join(tickers),
        period="1mo",
        interval="1d",
        group_by="ticker",
        threads=True,
        progress=False,
    )

    results = []
    for ticker in tickers:
        try:
            df = data[ticker] if len(tickers) > 1 else data
            df = df.dropna()
            if len(df) < 5:
                continue

            last_close = df["Close"].iloc[-1]
            prev_close = df["Close"].iloc[-2]
            pct_change = ((last_close - prev_close) / prev_close) * 100

            last_volume = df["Volume"].iloc[-1]
            avg_volume = df["Volume"].iloc[:-1].tail(20).mean()
            volume_ratio = (last_volume / avg_volume) if avg_volume else 0

            # หมายเหตุ: ระหว่างตลาดเปิด แท่ง volume ของ "วันนี้" จะสะสมไม่ครบวัน เทียบกับ
            # ค่าเฉลี่ย 20 วันเต็มแล้วต่ำกว่าจริงเสมอ จึงใช้ % change เป็นเกณฑ์หลัก (gate)
            # ส่วน volume_ratio ใช้ถ่วงน้ำหนักคะแนนเพื่อจัดอันดับ ไม่ใช้กรองออกแบบ AND
            if abs(pct_change) >= MIN_PCT_CHANGE:
                momentum_score = abs(pct_change) * max(volume_ratio, MIN_VOLUME_RATIO)
                results.append({
                    "ticker": ticker,
                    "pct_change": round(pct_change, 2),
                    "volume_ratio": round(volume_ratio, 2),
                    "momentum_score": round(momentum_score, 2),
                })
        except Exception as e:
            print(f"⚠️ Skip {ticker}: {e}")
            continue

    results.sort(key=lambda x: x["momentum_score"], reverse=True)
    return results


def update_target_tickers(top_n=5):
    """สแกน universe ทั้งหมด คัด top_n ตัวที่ซิ่งสุด เขียนทับ target_ticker.txt"""
    universe = load_universe()
    movers = scan_movers(universe)

    if not movers:
        print("💤 ไม่มีหุ้นตัวไหนผ่านเกณฑ์ 'ซิ่ง' วันนี้ — target_ticker.txt จะไม่ถูกแก้ไข")
        return []

    top_movers = movers[:top_n]

    with open(TARGET_FILE, "w") as f:
        for m in top_movers:
            f.write(m["ticker"] + "\n")

    print(f"✅ พบ {len(movers)} ตัวที่ซิ่ง คัด Top {len(top_movers)} เขียนลง {TARGET_FILE}:")
    for m in top_movers:
        print(f"   {m['ticker']}: {m['pct_change']:+.2f}% | Volume x{m['volume_ratio']:.1f} | Score {m['momentum_score']:.1f}")

    return [m["ticker"] for m in top_movers]


if __name__ == "__main__":
    update_target_tickers()
