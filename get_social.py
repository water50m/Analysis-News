# main_social.py
import time
import requests
from services import analyze_content, send_line_push, TWITTER_BEARER_TOKEN, IMPACT_THRESHOLD

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
            # ส่งไปวิเคราะห์
            analysis = analyze_content("TWEET", user['handle'], tweets)
            
            if analysis and analysis.get('impact_score', 0) > IMPACT_THRESHOLD:
                
                # ดึงข้อมูลใหม่ที่ AI วิเคราะห์มาได้
                sector = analysis.get('affected_sector', 'General')
                ticker = analysis.get('specific_stock', user['default_stock'])
                score = analysis.get('impact_score', 0)
                summary = analysis.get('summary_message', '')
                
                # 🎨 DESIGN: รูปแบบข้อความสไตล์ Social (ต่างจากข่าว)
                msg = f"⚡ FLASH UPDATE 🐦\n"
                msg += f"🗣️ ต้นทาง: {user['handle']}\n"
                msg += f"🎯 กระทบ: {ticker} ({sector})\n"
                msg += f"🌊 ความแรง: {'🔴'*score} ({score}/10)\n"
                msg += f"────────────────\n"
                msg += f"{summary}\n"
                msg += f"────────────────\n"
                msg += f"💡 มุมมอง AI: {analysis.get('reason')}"
                
                send_line_push(msg)
                print(f"✅ Alert sent for {user['handle']}")
            else:
                print(f"💤 Impact low ({analysis.get('impact_score') if analysis else 0})")
        else:
            print("⚠️ No tweets found")
            
        time.sleep(2)

if __name__ == "__main__":
    run_social_bot()