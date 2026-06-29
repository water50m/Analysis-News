# main_social.py
import time
import requests
from services import analyze_content, send_line_push, get_current_price, TWITTER_BEARER_TOKEN, IMPACT_THRESHOLD
from db_handler import save_prediction

def run_social_bot():
    print("\n🐦 --- STARTING SOCIAL BOT ---")
    
    # 📋 รายชื่อเป้าหมาย (ตัวอย่าง ID สมมติ - คุณต้องแก้เลข ID ให้ถูกต้อง)
    target_users = [
        {"id": "44196397", "handle": "@elonmusk", "default_stock": "TSLA"},
        {"id": "15550716", "handle": "@SECGov", "default_stock": "CRYPTO"},
        {"id": "22703645", "handle": "@federalreserve", "default_stock": "MARKET"},
        {"id": "1605", "handle": "@sama", "default_stock": "AI"},
        {"id": "34153254", "handle": "@JeffBezos", "default_stock": "AMZN"},
        {"id": "1636590253", "handle": "@tim_cook", "default_stock": "AAPL"},
        # ไปหา ID จริงที่ tweeterid.com มาใส่นะครับ
    ]
    
    if not TWITTER_BEARER_TOKEN:
        print("❌ Error: No Twitter Token found.")
        return

    headers = {"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"}
    
    for user in target_users:
        print(f"🔍 Checking Tweets: {user['handle']}")
        
        url = f"https://api.twitter.com/2/users/{user['id']}/tweets?max_results=5&exclude=retweets,replies"
        
        try:
            res = requests.get(url, headers=headers)
            tweets = res.json().get("data", [])
        except Exception as e:
            print(f"❌ API Error: {e}")
            tweets = []
            
        if tweets:
            analysis = analyze_content("TWEET", user['handle'], tweets)
            score = analysis.get('impact_score', 0) if analysis else 0
            
            if analysis and score > IMPACT_THRESHOLD:
                # 1. หาว่ากระทบหุ้นตัวไหน? (ใช้ที่ AI บอก หรือใช้ Default)
                detected_ticker = analysis.get('specific_stock')
                if not detected_ticker or detected_ticker == "GENERAL":
                    detected_ticker = user['default_stock']

                # 2. ดึงราคาของหุ้นตัวนั้น
                current_price = get_current_price(detected_ticker)

                # 3. บันทึกลง DB
                save_prediction(
                    symbol=detected_ticker,
                    source_type="TWEET",
                    summary=analysis.get('summary_message'),
                    direction=analysis.get('predicted_direction', 'NEUTRAL'),
                    score=score,
                    current_price=current_price,
                    target_price=analysis.get('target_price'),
                    stop_loss_price=analysis.get('stop_loss_price'),
                    time_horizon_days=analysis.get('time_horizon_days')
                )

                # 4. ส่ง LINE
                direction_emoji = "📈" if analysis.get('predicted_direction') == "UP" else "📉"
                msg = f"⚡ FLASH UPDATE 🐦\n"
                msg += f"🗣️ ต้นทาง: {user['handle']}\n"
                msg += f"🎯 กระทบ: {detected_ticker} ({analysis.get('affected_sector')})\n"
                msg += f"🔮 AI ทาย: {analysis.get('predicted_direction')} {direction_emoji}\n"
                msg += f"🌊 ความแรง: {'🔴'*score} ({score}/10)\n"
                msg += f"💰 ราคาตอนทาย: ${current_price}\n"
                msg += f"🎯 เป้าหมาย: ${analysis.get('target_price', 'N/A')} | 🛑 ตัดขาดทุน: ${analysis.get('stop_loss_price', 'N/A')}\n"
                msg += f"⏱️ กรอบเวลา: {analysis.get('time_horizon_days', 'N/A')} วัน\n"
                msg += f"────────────────\n{analysis.get('summary_message')}\n────────────────\n💡 {analysis.get('reason')}"
                
                send_line_push(msg)
                print(f"✅ Alert sent & Saved for {user['handle']} -> {detected_ticker}")
            else:
                print(f"💤 Impact low ({score})")
            
        time.sleep(2)

if __name__ == "__main__":
    run_social_bot()