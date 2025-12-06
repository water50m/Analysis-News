# main_news.py
import time
import requests
# 👇 Import เพิ่ม: get_current_price และ save_prediction
from services import analyze_content, send_line_push, get_current_price, get_market_context, ALPHA_VANTAGE_API_KEY, IMPACT_THRESHOLD
from db_handler import save_prediction

def run_news_bot():
    print("\n📰 --- STARTING NEWS BOT (Smart Filter Mode) ---")
    
    # 1. ดึงภาพรวมตลาด
    print("🌍 Fetching Global Market Context...")
    market_context = get_market_context()

    try:
        with open("target_ticker.txt", "r") as f:
            tickers = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("❌ ไม่พบไฟล์ target_ticker.txt")
        return

    for i, ticker in enumerate(tickers):
        print(f"🔍 Checking News for: {ticker}")
        
        # ✅ แก้ไข 1: ขอ max limit = 50 ไปเลย (ใช้ 1 request เท่าเดิม ไม่เสียของ)
        url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={ticker}&sort=LATEST&limit=50&apikey={ALPHA_VANTAGE_API_KEY}"
        
        try:
            res = requests.get(url).json()
            all_feed = res.get("feed", [])
        except Exception as e:
            print(f"❌ API Error: {e}")
            all_feed = []

        # ✅ แก้ไข 2: ระบบคัดกรองข่าว (Smart Filter)
        filtered_feed = []
        if all_feed:
            print(f"   - Found {len(all_feed)} raw news items.")
            
            # วนลูปเช็คความเกี่ยวข้อง (Relevance Score)
            sorted_feed = []
            for news in all_feed:
                # หา score ของ ticker ปัจจุบันในข่าวนี้
                ticker_relevance = 0.0
                for topic in news.get('ticker_sentiment', []):
                    if topic['ticker'] == ticker:
                        ticker_relevance = float(topic['relevance_score'])
                        break
                
                # เก็บไว้เพื่อเรียงลำดับ
                sorted_feed.append((ticker_relevance, news))
            
            # เรียงจากมากไปน้อย (Score สูงสุดขึ้นก่อน)
            sorted_feed.sort(key=lambda x: x[0], reverse=True)
            
            # ตัดเอาเฉพาะ 10 อันดับแรกที่เกี่ยวข้องที่สุด
            # (หรือเอาข่าวที่มี Score > 0.5 เท่านั้นก็ได้)
            filtered_feed = [item[1] for item in sorted_feed[:10]]
            
            print(f"   - Filtered down to top {len(filtered_feed)} most relevant items.")

        # 3. ส่งให้ AI วิเคราะห์ (เฉพาะเนื้อๆ เน้นๆ)
        if filtered_feed:
            analysis = analyze_content("NEWS", ticker, filtered_feed, market_context=market_context)
            
            score = analysis.get('impact_score', 0) if analysis else 0

            if analysis and score > IMPACT_THRESHOLD:
                current_price = get_current_price(ticker)
                
                # บันทึกลง DB
                save_prediction(
                    symbol=ticker,
                    source_type="NEWS",
                    summary=analysis.get('summary_message'),
                    direction=analysis.get('predicted_direction', 'NEUTRAL'),
                    score=score,
                    current_price=current_price
                )

                # ส่ง LINE
                direction_emoji = "📈" if analysis.get('predicted_direction') == "UP" else "📉"
                msg = f"📰 ข่าวหุ้น: {ticker}\n"
                msg += f"🔮 AI ทาย: {analysis.get('predicted_direction')} {direction_emoji}\n"
                msg += f"🔥 ความแรง: {score}/10\n"
                msg += f"💰 ราคา: ${current_price}\n"
                msg += f"------------------\n{analysis.get('summary_message')}\n------------------\n💡 {analysis.get('reason')}"
                
                send_line_push(msg)
                print(f"✅ Alert sent for {ticker}")
            else:
                print(f"💤 Impact low ({score})")
        else:
            print("⚠️ No relevant news found")

        if i < len(tickers) - 1:
            print("⏳ Waiting 15s...")
            time.sleep(15)

if __name__ == "__main__":
    run_news_bot()

