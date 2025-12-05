# main_news.py
import time
import requests
# 👇 Import ฟังก์ชันจากไฟล์ services.py มาใช้
from services import analyze_content, send_line_push, ALPHA_VANTAGE_API_KEY, IMPACT_THRESHOLD

def run_news_bot():
    print("\n📰 --- STARTING NEWS BOT ---")
    
    # อ่านรายชื่อหุ้น
    try:
        with open("target_ticker.txt", "r") as f:
            tickers = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("❌ ไม่พบไฟล์ target_ticker.txt")
        return

    for i, ticker in enumerate(tickers):
        print(f"🔍 Checking News for: {ticker}")
        
        # 1. ดึงข่าว (Logic เฉพาะของ Alpha Vantage)
        url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={ticker}&sort=LATEST&limit=10&apikey={ALPHA_VANTAGE_API_KEY}"
        
        try:
            res = requests.get(url).json()
            feed = res.get("feed", [])
        except Exception as e:
            print(f"❌ API Error: {e}")
            feed = []

        # 2. ส่งไปวิเคราะห์ (ใช้ฟังก์ชันกลาง)
        if feed:
            # ส่งแค่ 5 ข่าวล่าสุด
            analysis = analyze_content("NEWS", ticker, feed[:5])
            
            if analysis and analysis['impact_score'] > IMPACT_THRESHOLD:
                msg = f"📰 ข่าวหุ้น: {ticker}\n🔥 ความแรง: {analysis['impact_score']}/10\n\n{analysis['summary_message']}\n\n💡 {analysis['reason']}"
                send_line_push(msg)
                print(f"✅ Alert sent for {ticker}")
            else:
                score = analysis.get('impact_score', 0) if analysis else 0
                print(f"💤 Impact low ({score})")
        else:
            print("⚠️ No news found")

        # Rate Limit
        if i < len(tickers) - 1:
            print("⏳ Waiting 15s...")
            time.sleep(15)

if __name__ == "__main__":
    run_news_bot()