import os
import json
import requests
import google.generativeai as genai
from dotenv import load_dotenv


# Import DB Handler (ตรวจสอบว่าใช้ Supabase หรือ SQLite ตามที่คุณเลือก)
# ถ้าใช้ Supabase ให้ import แบบนี้:
from db_handler import get_accuracy_stats, get_learning_examples

load_dotenv()

# --- Configuration ---
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_GROUP_ID = os.getenv("LINE_GROUP_ID")

IMPACT_THRESHOLD = 5

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ============================
# 📤 Function: ส่ง LINE
# ============================
def send_line_push(message):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {"to": LINE_GROUP_ID, "messages": [{"type": "text", "text": message}]}
    
    try:
        requests.post(url, headers=headers, json=payload)
    except Exception as e:
        print(f"❌ Line Error: {e}")

# ============================
# 💰 Function: ดึงราคาปัจจุบัน
# ============================
def get_current_price(ticker):
    # ถ้าไม่มี Ticker หรือเป็น General ให้ข้าม
    if not ticker or ticker == "GENERAL": return 0.0
    
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={ALPHA_VANTAGE_API_KEY}"
    try:
        data = requests.get(url).json()
        return float(data["Global Quote"]["05. price"])
    except:
        return 0.0

# ============================
# 🧠 Function: วิเคราะห์ด้วย AI (รวมร่างครบทุกฟีเจอร์)
# ============================
def analyze_content(source_type, topic, content_data):
    print(f"🧠 กำลังวิเคราะห์ {source_type} ของ {topic}...")
    
    data_text = json.dumps(content_data, indent=2)

    # 1. ดึงข้อมูลการเรียนรู้ (Feedback Loop)
    try:
        total, correct = get_accuracy_stats()
        acc_percent = (correct/total)*100 if total > 0 else 0
        mistakes = get_learning_examples(limit=3)
    except:
        acc_percent = 0
        mistakes = []

    # เตรียมข้อความสอนใจ (Lesson Learned)
    mistakes_text = ""
    if mistakes:
        mistakes_text = "Here are your past MISTAKES (Learn from them to improve):\n"
        for m in mistakes:
            mistakes_text += f"- Context: {m.get('news_summary', '')[:50]}...\n"
            mistakes_text += f"  You predicted: {m.get('predicted_direction')} | Actual: {'DOWN' if m.get('predicted_direction') == 'UP' else 'UP'}\n"

    # 2. แยก Prompt ตามประเภท (News vs Tweet)
    if source_type == "TWEET":
        # --- Prompt สำหรับ Social ---
        prompt = f"""
        Role: Senior Market Sentiment Analyst.
        
        [YOUR PERFORMANCE]
        Current Accuracy: {acc_percent:.1f}%
        {mistakes_text}

        Task: Analyze tweets from influencer: {topic}
        [TWEETS START]
        {data_text}
        [TWEETS END]

        Analyze hidden market signals and sarcasm.
        1. Impact Score (1-10): Urgency?
        2. Prediction: Will the related asset go UP or DOWN in 24h?
        3. Specific Asset: Ticker symbol affected (e.g. TSLA, DOGE).
        4. Summary (Thai): Informal/Social tone.

        Response JSON Format ONLY:
        {{
            "impact_score": <int>,
            "predicted_direction": "UP/DOWN/NEUTRAL",
            "specific_stock": "<Ticker Symbol>",
            "affected_sector": "<Sector>",
            "summary_message": "<Thai Summary>",
            "reason": "<Reason>"
        }}
        """
    else:
        # --- Prompt สำหรับ News ---
        prompt = f"""
        Role: Professional Stock Trader.

        [YOUR PERFORMANCE]
        Current Accuracy: {acc_percent:.1f}%
        {mistakes_text}

        Task: Analyze news for ticker: {topic}
        [NEWS START]
        {data_text}
        [NEWS END]

        1. Impact Score (1-10): Market moving potential?
        2. Prediction: Will price go UP or DOWN in 24h?
        3. Summary (Thai): Formal tone.

        Response JSON Format ONLY:
        {{
            "impact_score": <int>,
            "predicted_direction": "UP/DOWN/NEUTRAL",
            "summary_message": "<Thai Summary>",
            "reason": "<Reason>"
        }}
        """

    # 3. ส่งเข้า Gemini (Fail-over Logic)
    models = ['models/gemini-1.5-pro', 'models/gemini-2.0-flash', 'models/gemini-1.5-flash']
    
    for model_name in models:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                prompt, 
                generation_config={"response_mime_type": "application/json"}
            )
            
            result = json.loads(response.text)
            
            # ป้องกัน AI ส่ง List กลับมา
            if isinstance(result, list):
                if len(result) > 0: result = result[0]
                else: return None

            return result
            
        except Exception as e:
            # print(f"⚠️ Model {model_name} failed: {e}") # Uncomment ถ้าอยากดู error
            continue
            
    print("❌ All AI models failed.")
    return None