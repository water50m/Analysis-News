# main_news.py
import time
import requests
# 👇 Import เพิ่ม: get_current_price และ save_prediction
from services import analyze_content, send_line_push, get_current_price, ALPHA_VANTAGE_API_KEY, IMPACT_THRESHOLD
from db_handler import save_prediction 

def run_news_bot():
    print("\n📰 --- STARTING NEWS BOT ---")
    
    try:
        with open("target_ticker.txt", "r") as f:
            tickers = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("❌ ไม่พบไฟล์ target_ticker.txt")
        return

    for i, ticker in enumerate(tickers):
        print(f"🔍 Checking News for: {ticker}")
        
        url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={ticker}&sort=LATEST&limit=10&apikey={ALPHA_VANTAGE_API_KEY}"
        
        try:
            res = requests.get(url).json()
            feed = res.get("feed", [])
        except Exception as e:
            print(f"❌ API Error: {e}")
            feed = []

        if feed:
            # วิเคราะห์
            analysis = analyze_content("NEWS", ticker, feed[:5])
            
            score = analysis.get('impact_score', 0) if analysis else 0

            if analysis and score > IMPACT_THRESHOLD:
                # 1. ดึงราคาปัจจุบัน (เพื่อเอาไว้ตรวจคำตอบทีหลัง)
                current_price = get_current_price(ticker)
                
                # 2. บันทึกลง Supabase 💾
                save_prediction(
                    symbol=ticker,
                    source_type="NEWS",
                    summary=analysis.get('summary_message'),
                    direction=analysis.get('predicted_direction', 'NEUTRAL'),
                    score=score,
                    current_price=current_price
                )

                # 3. ส่ง LINE
                direction_emoji = "📈" if analysis.get('predicted_direction') == "UP" else "📉"
                msg = f"📰 ข่าวหุ้น: {ticker}\n"
                msg += f"🔮 AI ทาย: {analysis.get('predicted_direction')} {direction_emoji}\n"
                msg += f"🔥 ความแรง: {score}/10\n"
                msg += f"💰 ราคาตอนทาย: ${current_price}\n"
                msg += f"------------------\n{analysis['summary_message']}\n------------------\n💡 {analysis['reason']}"
                
                send_line_push(msg)
                print(f"✅ Alert sent & Saved for {ticker}")
            else:
                print(f"💤 Impact low ({score})")
        else:
            print("⚠️ No news found")

        if i < len(tickers) - 1:
            print("⏳ Waiting 15s...")
            time.sleep(15)

if __name__ == "__main__":
    run_news_bot()