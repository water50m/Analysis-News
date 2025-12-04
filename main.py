import os
import requests
import google.generativeai as genai
import json
from dotenv import load_dotenv
import time

# โหลดค่าจากไฟล์ .env
load_dotenv()

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

#  LINE
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_GROUP_ID = os.getenv("LINE_GROUP_ID")


IMPACT_THRESHOLD = 5  # คะแนนขั้นต่ำที่จะให้ส่งไลน์ (เกิน 5 ถึงส่ง)

genai.configure(api_key=GEMINI_API_KEY)


# ==========================================
# 1. ดึงข้อมูล (Data Fetching)
# ==========================================
def get_stock_news(ticker):
    print(f"📥 กำลังดึงข้อมูลข่าวของ {ticker}...")
    # เพิ่ม limit เป็น 20 เพื่อให้ AI มีข้อมูลให้คัดเยอะขึ้น
    url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={ticker}&sort=LATEST&limit=20&apikey={ALPHA_VANTAGE_API_KEY}"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if "feed" in data:
            news_items = []
            for item in data["feed"][:10]: # ส่งให้ AI แค่ 10 ข่าวล่าสุดพอก่อน (ประหยัด Token)
                news_items.append({
                    "title": item.get("title"),
                    "summary": item.get("summary"),
                    "overall_sentiment_score": item.get("overall_sentiment_score")
                })
            return news_items
        else:
            print("⚠️ ไม่พบข้อมูลข่าว หรือ API Limit เต็ม")
            return None
    except Exception as e:
        print(f"❌ Error fetching news: {e}")
        return None

# ==========================================
# 2. ประมวลผลด้วย AI (Gemini Processing)
# ==========================================
def analyze_with_gemini(ticker, news_data):
    print(f"🧠 กำลังให้ Gemini วิเคราะห์และให้คะแนน...")
    
    news_text = json.dumps(news_data)
    
    # Prompt (เหมือนเดิม)
    prompt = f"""
    You are a professional stock analyst. Analyze the following news for ticker: {ticker}.
    
    [NEWS DATA]
    {news_text}
    [END DATA]

    Task:
    1. Assess the potential impact of these news items on the stock price on a scale of 1-10.
       (1 = Noise/Irrelevant, 10 = Critical/Market Moving like Earnings, M&A, CEO change)
    2. Summarize the key takeaways in Thai language.
    
    Response Format:
    You MUST return ONLY a valid JSON object strictly following this structure:
    {{
        "impact_score": <integer 1-10>,
        "summary_message": "<Your summary in Thai (3-4 lines), include sentiment trend>",
        "reason": "<Short reason for the score>"
    }}
    """
    
    # =========================================================
    # 🔄 MODEL PRIORITY LIST (เรียงลำดับความสำคัญ)
    # 1. ลองตัวใหม่ล่าสุด (Gemini 3)
    # 2. ถ้าไม่ได้ ให้ลองตัวเสถียร (Gemini 2.5 Pro)
    # 3. ถ้าไม่ได้อีก ให้ลองตัวไว (Gemini 2.5 Flash)
    # =========================================================
    models_to_try = [
        'models/gemini-3-pro-preview', 
        'models/gemini-2.5-pro',
        'models/gemini-2.5-flash',
        'models/gemini-1.5-pro'
    ]

    for model_name in models_to_try:
        try:
            print(f"⚡ กำลังทดสอบเชื่อมต่อกับโมเดล: {model_name} ...")
            
            model = genai.GenerativeModel(model_name)
            
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"} 
            )
            
            # ถ้ามาถึงตรงนี้แปลว่าสำเร็จ ไม่ Error
            result_json = json.loads(response.text)
            print(f"✅ สำเร็จ! ใช้งานโมเดล {model_name} ได้")
            return result_json
            
        except Exception as e:
            # ถ้า Error ให้แจ้งเตือนแล้ววนลูปไปตัวถัดไป
            print(f"⚠️ โมเดล {model_name} มีปัญหา")
            print("🔄 กำลังสลับไปใช้โมเดลสำรองลำดับถัดไป...")
            continue # ข้ามไปรอบถัดไป (โมเดลตัวต่อไป)

    # ถ้าวนครบทุกตัวแล้วยัง Error หมดเลย
    print("❌ Error: ไม่สามารถใช้งานโมเดลใดๆ ได้เลย")
    return None

# ==========================================
# 3. แจ้งเตือน (LINE Notification)
# ==========================================
def send_line_push(message):
    """
    ส่งข้อความเข้า Group โดยระบุ Group ID ผ่าน LINE Messaging API
    """
    print(f"📲 กำลังส่งข้อมูลเข้า LINE Group ID: {LINE_GROUP_ID}...")
    
    url = "https://api.line.me/v2/bot/message/push"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    
    # โครงสร้าง Payload สำหรับ Messaging API
    payload = {
        "to": LINE_GROUP_ID,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }
    
    try:
        # ต้องใช้ json=payload เพื่อให้ requests แปลงเป็น JSON string ให้
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            print("✅ ส่ง LINE สำเร็จ!")
        else:
            print(f"❌ ส่ง LINE ไม่สำเร็จ: {response.status_code}")
            print(response.text) # ปริ้นดู error จาก LINE
    except Exception as e:
        print(f"❌ Error sending Line: {e}")
# ==========================================
# 4. Helper Functions (ฟังก์ชันช่วยทำงาน)
# ==========================================

def load_tickers(filename="target_ticker.txt"):
    """อ่านรายชื่อหุ้นจากไฟล์ และแปลงเป็น List"""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            # list comprehension: อ่านทีละบรรทัด, ตัดช่องว่าง, เอาเฉพาะบรรทัดที่มีตัวหนังสือ
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"❌ Error: ไม่พบไฟล์ {filename}")
        return []

def run_analysis_for_ticker(ticker):
    """
    Function นี้รับผิดชอบ Process ของหุ้น 1 ตัวแบบจบในตัว
    (ดึงข่าว -> วิเคราะห์ -> ส่งไลน์)
    """
    print(f"\n{'='*30}")
    print(f"🔍 เริ่มดำเนินการ: {ticker}")
    print(f"{'='*30}")

    # 1. ดึงข่าว
    news = get_stock_news(ticker)
    if not news:
        print(f"⚠️ {ticker}: ไม่พบข้อมูลข่าว หรือ API มีปัญหา")
        return

    # 2. วิเคราะห์ AI
    result = analyze_with_gemini(ticker, news)
    if not result:
        print(f"❌ {ticker}: วิเคราะห์ไม่สำเร็จ (Gemini Error)")
        return

    # 3. ตรวจสอบผลลัพธ์
    score = result.get("impact_score", 0)
    summary = result.get("summary_message", "")
    reason = result.get("reason", "")

    print(f"📊 {ticker} Score: {score}/10")

    # 4. ส่ง Line ถ้าคะแนนถึง
    if score > IMPACT_THRESHOLD:
        print(f"✅ {ticker}: คะแนนเกินเกณฑ์ ({score}) -> กำลังส่ง LINE...")
        
        final_msg = f"🚨 แจ้งเตือนหุ้น {ticker}\n"
        final_msg += f"🔥 ความรุนแรง: {score}/10\n"
        final_msg += f"------------------\n"
        final_msg += f"{summary}\n"
        final_msg += f"------------------\n"
        final_msg += f"💡 เหตุผล: {reason}"
        
        send_line_push(final_msg)
    else:
        print(f"💤 {ticker}: ข่าวไม่รุนแรงพอ ({score}) -> ไม่ส่ง")

# ==========================================
# 🚀 MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    # 1. โหลดรายชื่อหุ้น
    tickers = load_tickers("target_ticker.txt")
    
    if not tickers:
        print("จบการทำงาน: ไม่มีรายชื่อหุ้นในไฟล์")
        exit()

    print(f"📋 พบรายชื่อหุ้นทั้งหมด {len(tickers)} ตัว: {tickers}")

    # 2. วนลูปทำงาน
    for i, ticker in enumerate(tickers):
        
        # เรียกใช้ฟังก์ชันที่เราแยกออกมา
        run_analysis_for_ticker(ticker)
        
        # Logic การหน่วงเวลา (Rate Limiting)
        # เช็คว่าถ้าไม่ใช่ตัวสุดท้าย ให้รอ
        is_last_ticker = (i == len(tickers) - 1)
        if not is_last_ticker:
            print("⏳ รอ 15 วินาที เพื่อไม่ให้เกินโควต้า API...")
            time.sleep(15) 

    print("\n🏁 จบการทำงานครบทุกตัวแล้ว")