# services.py
import os
import requests
import json
import google.generativeai as genai
from dotenv import load_dotenv

# 1. โหลด Config ตั้งแต่เริ่ม
load_dotenv()

ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_GROUP_ID = os.getenv("LINE_GROUP_ID")

IMPACT_THRESHOLD = 5

# ตั้งค่า AI
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
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            print(f"❌ Line Error: {response.text}")
    except Exception as e:
        print(f"❌ Line Exception: {e}")

# ============================
# 🧠 Function: วิเคราะห์ด้วย AI
# ============================


def analyze_content(source_type, topic, content_data):
    print(f"🧠 กำลังวิเคราะห์ {source_type} ของ {topic}...")
    
    data_text = json.dumps(content_data, indent=2)
    
    # ==========================================
    # 📝 PROMPT STRATEGY
    # ==========================================
    if source_type == "TWEET":
        # Prompt สำหรับ Social (เน้น Sector/Stock/Impact)
        prompt = f"""
        Role: Senior Market Sentiment Analyst.
        Task: Analyze tweets from influencer: {topic}
        
        [TWEETS START]
        {data_text}
        [TWEETS END]

        Analyze the hidden market signals.
        1. Impact Score (1-10): Urgency and market moving potential.
        2. Affected Sector: Which industry is affected? (e.g., EV, AI, Crypto, Banking).
        3. Specific Stock/Asset: Which specific ticker symbol is most affected? (e.g., TSLA, BTC, NVDA). If unsure, use "GENERAL".
        4. Summary (Thai): Short, punchy summary (informal/social tone).
        
        Response JSON Format ONLY:
        {{
            "impact_score": <int>,
            "affected_sector": "<Sector Name>",
            "specific_stock": "<Ticker Symbol>",
            "summary_message": "<Thai Summary>",
            "reason": "<Reason>"
        }}
        """
    else:
        # Prompt สำหรับ News (แบบเดิม เป็นทางการ)
        prompt = f"""
            Role: Professional Stock Analyst.
            Task: Analyze this {source_type} data related to: {topic}
            
            [DATA START]
            {data_text}
            [DATA END]

            1. Score Impact (1-10): How much does this affect the stock market/price?
            (1=Noise, 10=Market Crash/Boom/Major News)
            2. Summary (Thai): Summarize key points in Thai.
            
            Response Format (JSON ONLY):
            {{
                "impact_score": <int>,
                "summary_message": "<Thai Summary>",
                "reason": "<Short Reason>"
            }}
        """
      # Fail-over Models
    models = ['models/gemini-2.0-flash', 'models/gemini-1.5-pro', 'models/gemini-1.5-flash']
    
    for model_name in models:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                prompt, 
                generation_config={"response_mime_type": "application/json"}
            )
            
            # --- แก้ไขตรงนี้ (START) ---
            result = json.loads(response.text)
            
            # 🛡️ ป้องกันกรณี AI ส่งกลับมาเป็น List (เช่น [{"impact_score": 8}])
            if isinstance(result, list):
                if len(result) > 0:
                    return result[0] # ดึงตัวแรกออกมาใช้
                else:
                    return None # ถ้า List ว่างเปล่า
            
            return result
            # --- แก้ไขตรงนี้ (END) ---
            
        except Exception:
            continue
            
    print("❌ All AI models failed.")
    return None