"""Screener: สแกนหุ้นจาก watchlist_universe.txt หา 'หุ้นซิ่ง' ของวันนี้ (% เปลี่ยนแปลง + volume spike)
ใช้ yfinance batch download เท่านั้น — ไม่มี API key/quota จึงสแกนได้หลายร้อยตัวพร้อมกันโดยไม่เสียค่าใช้จ่าย
ผลลัพธ์ top N จะถูกเขียนทับ target_ticker.txt ให้ get_news.py ไปวิเคราะห์ลึกต่อ (ที่ใช้ quota จำกัด)"""

import yfinance as yf

from get_fundamentals import get_float_momentum_multiplier
from get_social_buzz import get_trending_symbols

UNIVERSE_FILE = "watchlist_universe.txt"
TARGET_FILE = "target_ticker.txt"

MIN_PCT_CHANGE = 3.0      # % เปลี่ยนแปลงขั้นต่ำที่ถือว่า "ซิ่ง"
MIN_GAP_PCT = 4.0         # % gap ขั้นต่ำช่วง pre-market/after-hours ที่ถือว่าน่าสนใจ


def load_universe(include_trending=True):
    """รวม watchlist คงที่ + หุ้นที่กำลัง trending บน StockTwits (จับตัวที่ไม่อยู่ใน watchlist
    แต่ดันมาฮือฮาขึ้นมาเฉยๆ) ตัวที่ดึง trending ไม่ได้/error ก็ไม่กระทบ ใช้ watchlist เดิมต่อได้"""
    try:
        with open(UNIVERSE_FILE, "r") as f:
            universe = [line.strip().upper() for line in f
                        if line.strip() and not line.strip().startswith("#")]
    except FileNotFoundError:
        print(f"❌ ไม่พบไฟล์ {UNIVERSE_FILE}")
        universe = []

    if include_trending:
        trending = get_trending_symbols()
        if trending:
            print(f"📈 เพิ่ม {len(trending)} ตัวที่ trending จาก StockTwits เข้า universe")
            universe = list(dict.fromkeys(universe + [t.upper() for t in trending]))

    return universe


def _pace_normalized_volume_ratio(intraday_df, lookback_days=5):
    """เทียบ volume ของ 'วันนี้จนถึงเวลานี้' กับค่าเฉลี่ยของช่วงเวลาเดียวกันใน lookback_days วันก่อน
    แม่นยำกว่าการเทียบกับ full-day average ตรงๆ เพราะวันนี้ยังไม่ปิดตลาด (แท่งสะสมไม่ครบวัน)"""
    df = intraday_df.dropna()
    if df.empty:
        return 0

    dates = sorted(set(df.index.date))
    if len(dates) < 2:
        return 0

    today = dates[-1]
    today_df = df[df.index.date == today]
    if today_df.empty:
        return 0

    cutoff_time = today_df.index[-1].time()
    today_volume_sofar = today_df["Volume"].sum()

    past_sums = []
    for d in dates[:-1][-lookback_days:]:
        day_df = df[df.index.date == d]
        sofar = day_df[day_df.index.time <= cutoff_time]["Volume"].sum()
        if sofar > 0:
            past_sums.append(sofar)

    avg_past_sofar = sum(past_sums) / len(past_sums) if past_sums else 0
    return (today_volume_sofar / avg_past_sofar) if avg_past_sofar else 0


def scan_movers(tickers):
    """สแกนทุก ticker พร้อมกันด้วย yfinance batch download คืน list of dict ที่ผ่านเกณฑ์ 'ซิ่ง'"""
    if not tickers:
        return []

    print(f"🔍 Scanning {len(tickers)} tickers...")
    daily = yf.download(
        tickers=" ".join(tickers),
        period="1mo",
        interval="1d",
        group_by="ticker",
        threads=True,
        progress=False,
    )
    intraday = yf.download(
        tickers=" ".join(tickers),
        period="6d",
        interval="5m",
        group_by="ticker",
        threads=True,
        progress=False,
    )

    results = []
    for ticker in tickers:
        try:
            df = (daily[ticker] if len(tickers) > 1 else daily).dropna()
            if len(df) < 5:
                continue

            last_close = df["Close"].iloc[-1]
            prev_close = df["Close"].iloc[-2]
            pct_change = ((last_close - prev_close) / prev_close) * 100

            intraday_df = intraday[ticker] if len(tickers) > 1 else intraday
            volume_ratio = _pace_normalized_volume_ratio(intraday_df)

            if abs(pct_change) >= MIN_PCT_CHANGE:
                # เช็ค float เฉพาะตัวที่ผ่านเกณฑ์ %change แล้ว (กันยิง Finnhub ทุกตัวในทุกรอบสแกน)
                float_multiplier = get_float_momentum_multiplier(ticker)
                # volume_ratio เป็น pace-normalized แล้ว เชื่อค่าจริงได้ ไม่ต้อง floor ปลอม
                # floor ที่ 1.0 ไว้กันแค่กรณี data ขาด (volume_ratio=0) ไม่ให้ momentum_score เป็น 0 ไปด้วย
                momentum_score = abs(pct_change) * max(volume_ratio, 1.0) * float_multiplier
                results.append({
                    "ticker": ticker,
                    "pct_change": round(pct_change, 2),
                    "volume_ratio": round(volume_ratio, 2),
                    "float_multiplier": float_multiplier,
                    "momentum_score": round(momentum_score, 2),
                })
        except Exception as e:
            print(f"⚠️ Skip {ticker}: {e}")
            continue

    results.sort(key=lambda x: x["momentum_score"], reverse=True)
    return results


def scan_premarket_gaps(tickers):
    """สแกนหา gap ช่วง pre-market/after-hours เทียบกับราคาปิดตลาดปกติของวันก่อนหน้า
    ใช้ตอนตลาดยังไม่เปิด/ปิดไปแล้ว ที่ scan_movers() แบบ daily bar มองไม่เห็น"""
    if not tickers:
        return []

    print(f"🌅 Scanning {len(tickers)} tickers for pre/after-market gaps...")

    daily = yf.download(tickers=" ".join(tickers), period="5d", interval="1d",
                         group_by="ticker", threads=True, progress=False)
    extended = yf.download(tickers=" ".join(tickers), period="2d", interval="5m",
                            prepost=True, group_by="ticker", threads=True, progress=False)

    results = []
    for ticker in tickers:
        try:
            daily_df = (daily[ticker] if len(tickers) > 1 else daily).dropna()
            ext_df = (extended[ticker] if len(tickers) > 1 else extended).dropna()
            if len(daily_df) < 2 or ext_df.empty:
                continue

            # iloc[-1] ของ daily bar คือ "วันนี้" ที่ยังไม่ปิด (ราคายังขยับอยู่ระหว่างวัน)
            # ต้องใช้ iloc[-2] = ราคาปิดที่ "ปิดจริงแล้ว" ของวันก่อนหน้า มาเทียบกับ gap
            prev_regular_close = daily_df["Close"].iloc[-2]
            latest_extended_price = ext_df["Close"].iloc[-1]

            gap_pct = ((latest_extended_price - prev_regular_close) / prev_regular_close) * 100

            if abs(gap_pct) >= MIN_GAP_PCT:
                float_multiplier = get_float_momentum_multiplier(ticker)
                results.append({
                    "ticker": ticker,
                    "gap_pct": round(gap_pct, 2),
                    "float_multiplier": float_multiplier,
                    "momentum_score": round(abs(gap_pct) * float_multiplier, 2),
                })
        except Exception as e:
            print(f"⚠️ Skip {ticker}: {e}")
            continue

    results.sort(key=lambda x: x["momentum_score"], reverse=True)
    return results


def update_target_tickers_premarket(top_n=5):
    """สแกนหา gap pre-market/after-hours คัด top_n เขียนทับ target_ticker.txt"""
    universe = load_universe()
    movers = scan_premarket_gaps(universe)

    if not movers:
        print("💤 ไม่มี gap ผ่านเกณฑ์ตอนนี้ — target_ticker.txt จะไม่ถูกแก้ไข")
        return []

    top_movers = movers[:top_n]
    with open(TARGET_FILE, "w") as f:
        for m in top_movers:
            f.write(m["ticker"] + "\n")

    print(f"✅ พบ {len(movers)} ตัวมี gap คัด Top {len(top_movers)} เขียนลง {TARGET_FILE}:")
    for m in top_movers:
        print(f"   {m['ticker']}: gap {m['gap_pct']:+.2f}% | Float x{m['float_multiplier']:.1f} | Score {m['momentum_score']:.1f}")

    return [m["ticker"] for m in top_movers]


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
        print(f"   {m['ticker']}: {m['pct_change']:+.2f}% | Volume x{m['volume_ratio']:.1f} | "
              f"Float x{m['float_multiplier']:.1f} | Score {m['momentum_score']:.1f}")

    return [m["ticker"] for m in top_movers]


if __name__ == "__main__":
    update_target_tickers()
