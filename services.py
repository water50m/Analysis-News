import os
import json
import requests
import google.generativeai as genai
import yfinance as yf
import pandas as pd
from dotenv import load_dotenv
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
# 🧠 Function: วิเคราะห์ด้วย AI 
# ============================
def get_market_context():
    """เช็คดัชนีหลัก: S&P500 (^GSPC) และ Bitcoin (BTC-USD)"""
    indices = {
        "S&P 500": "^GSPC",
        "Bitcoin": "BTC-USD"
    }
    context_str = ""
    
    try:
        for name, ticker in indices.items():
            # ดึงข้อมูลย้อนหลัง 2 วันเพื่อเทียบราคา
            data = yf.Ticker(ticker).history(period="5d")
            if len(data) >= 2:
                last_close = data['Close'].iloc[-1]
                prev_close = data['Close'].iloc[-2]
                change_pct = ((last_close - prev_close) / prev_close) * 100
                
                trend = "UP" if change_pct > 0 else "DOWN"
                context_str += f"- {name}: {trend} ({change_pct:+.2f}%)\n"
    except Exception as e:
        print(f"⚠️ Market Context Error: {e}")
        return "Market data unavailable."
        
    return context_str.strip()

# ============================
# 📈 NEW: ฟังก์ชันดึงเทคนิคอล (RSI, SMA) จาก yfinance
# ============================
def get_technical_signals(ticker):
    """คำนวณ RSI และ Price vs SMA50"""
    if not ticker or ticker == "GENERAL": return "N/A"
    
    try:
        # ดึงข้อมูลย้อนหลัง 3 เดือน (เพื่อให้คำนวณ SMA50 ได้)
        df = yf.Ticker(ticker).history(period="3mo")
        
        if len(df) < 50: return "Not enough data"
        
        # 1. คำนวณ SMA 50
        sma50 = df['Close'].rolling(window=50).mean().iloc[-1]
        current_price = df['Close'].iloc[-1]
        
        # 2. คำนวณ RSI 14 (สูตรมาตรฐาน)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs)).iloc[-1]
        
        # สรุปผล
        trend = "BULLISH (Above SMA50)" if current_price > sma50 else "BEARISH (Below SMA50)"
        rsi_status = "Overbought (>70)" if rsi > 70 else "Oversold (<30)" if rsi < 30 else "Neutral"
        
        return f"Price: ${current_price:.2f} | SMA50: ${sma50:.2f} ({trend}) | RSI(14): {rsi:.1f} ({rsi_status})"
        
    except Exception as e:
        return f"Error: {e}"
    
# ============================
# 💰 Function: ดึงราคาปัจจุบัน (yfinance)
# ============================
def get_current_price(ticker):
    if not ticker or ticker == "GENERAL": return 0.0
    try:
        # ใช้ fast_info หรือ history(period='1d') ก็ได้
        return yf.Ticker(ticker).fast_info.last_price
    except:
        return 0.0

def send_line_push(message):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {"to": LINE_GROUP_ID, "messages": [{"type": "text", "text": message}]}
    try:
        requests.post(url, headers=headers, json=payload)
    except:
        pass
    
def analyze_content(source_type, topic, content_data, market_context=""):
    print(f"🧠 กำลังวิเคราะห์ {source_type} ของ {topic}...")

    technical_info = get_technical_signals(topic) if source_type == "NEWS" else "N/A"

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
        mistakes_text = "🚨 [LEARNING FROM PAST MISTAKES] (Analyze why you were wrong):\n"
        for m in mistakes:
            # 1. เพิ่มความยาวเป็น 100-150 ตัวอักษร เพื่อให้จับใจความได้
            summary = m.get('news_summary', '')[:120].replace('\n', ' ') 
            
            # 2. คำนวณเฉลย
            prediction = m.get('predicted_direction')
            actual = 'DOWN' if prediction == 'UP' else 'UP'
            
            # 3. จัด Format ให้ AI อ่านง่าย แยกบรรทัดชัดเจน
            mistakes_text += f"❌ Case ID {m.get('id')}:\n"
            mistakes_text += f"   - News Context: \"{summary}...\"\n"
            mistakes_text += f"   - Your Prediction: {prediction} (WRONG)\n"
            mistakes_text += f"   - Actual Market: {actual}\n\n"

    # 4. Base Prompt (ส่วนกลาง)
    base_sys_prompt = f"""
    Role: Professional Stock Trader & Analyst.

    [GLOBAL MARKET CONTEXT]
    {market_context}
    (Sentiment Guide: RED market = Be conservative. GREEN market = Supportive.)

    [YOUR PERFORMANCE]
    Your Current Accuracy: {acc_percent:.1f}%
    Here are your past MISTAKES: {mistakes_text}
    """

    # 5. แยก Prompt ตามประเภท (สำคัญ!)
    if source_type == "TWEET":
        prompt = f"""
        {base_sys_prompt}
        
        Task: Analyze tweets from influencer: {topic}
        [TWEETS]
        {json.dumps(content_data)}

        Analyze hidden signals, sarcasm, and meme-culture.
        1. Impact Score (1-10): Market moving potential?
        2. Prediction: Will the affected asset go UP or DOWN in 24h?
        3. Specific Stock: Identify the Ticker Symbol (e.g. TSLA, DOGE, BTC).
        4. Sector: e.g. EV, AI, Crypto.
        5. Summary (Thai): Informal/Social tone.

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
        # NEWS Prompt
        prompt = f"""
        {base_sys_prompt}

        [TECHNICAL INDICATORS] (For {topic})
        {technical_info}
        (RSI > 70 = Sell Risk, RSI < 30 = Buy Opportunity. Price > SMA50 = Uptrend.)

        Task: Analyze news for ticker: {topic}
        [NEWS]
        {json.dumps(content_data)}

        Combine Fundamental (News) + Technical (RSI/SMA) + Market Context.
        1. Impact Score (1-10).
        2. Prediction: UP or DOWN in 24h?
        3. Summary (Thai): Formal tone.

        Response JSON Format ONLY:
        {{
            "impact_score": <int>,
            "predicted_direction": "UP/DOWN/NEUTRAL",
            "summary_message": "<Thai Summary>",
            "reason": "<Reason>"
        }}
        """

    # 6. ส่งเข้า Gemini (Fail-over Logic)
    models = ['models/gemini-2.5-pro',  'models/gemini-1.5-pro', 'models/gemini-2.0-flash', 'models/gemini-1.5-flash']
    
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