import os
import json
import requests
import yfinance as yf
import pandas as pd
from dotenv import load_dotenv
from db_handler import get_accuracy_stats, get_learning_examples
from get_fundamentals import get_fundamental_context, get_fundamental_signal_score
from get_macro import get_macro_context, get_macro_signal_score
from signal_engine import compute_confluence, get_news_sentiment_score

# สามารถเลือก import ค่าย AI ที่ต้องการใช้
import google.generativeai as genai
from openai import OpenAI
import anthropic

load_dotenv()

# --- Configuration ---
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_GROUP_ID = os.getenv("LINE_GROUP_ID")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

IMPACT_THRESHOLD = 5

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("BASE_URL") # เผื่อใช้ DeepSeek
openai_client = None
if OPENAI_API_KEY:
    openai_client = OpenAI(
        api_key=OPENAI_API_KEY,
        base_url=BASE_URL if BASE_URL else None
    )
# ============================
# 🤖 AI Provider Functions (แยกการทำงานแต่ละค่าย)
# ============================
def call_claude(prompt):
    if not ANTHROPIC_API_KEY: return None
    
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    
    try:
        message = client.messages.create(
            model="claude-3-5-sonnet-20240620", # รุ่นเทพสุด
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        # Claude ส่งกลับเป็น Text เราต้องดึงออกมาแปลง JSON เอง
        content = message.content[0].text
        
        # บางที Claude จะเกริ่นนำ เราต้องหาปีกกา JSON
        json_start = content.find('{')
        json_end = content.rfind('}') + 1
        json_str = content[json_start:json_end]
        
        return json.loads(json_str)
        
    except Exception as e:
        print(f"❌ Claude Error: {e}")
        return None

def call_gemini(prompt):
    """เรียกใช้ Google Gemini"""
    models = ['models/gemini-2.5-pro',  'models/gemini-1.5-pro', 'models/gemini-2.0-flash', 'models/gemini-1.5-flash']
    
    for model_name in models:
        try:
            model = genai.GenerativeModel(model_name)
            res = model.generate_content(
                prompt, 
                generation_config={"response_mime_type": "application/json"}
            )
            return json.loads(res.text)
        except:
            continue
    return None

def call_openai(prompt):
    """เรียกใช้ OpenAI (GPT-4o) หรือ DeepSeek"""
    if not openai_client: return None
    
    # เลือกโมเดล (ถ้าใช้ DeepSeek ให้แก้เป็น 'deepseek-chat')
    model_name = "gpt-4o" if not BASE_URL else "deepseek-chat"
    
    try:
        response = openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a helpful financial assistant. You output JSON only."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"} # บังคับ JSON
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        print(f"❌ OpenAI Error: {e}")
        return None

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
# 💰 Function: ดึงราคาปัจจุบัน (yfinance)
# ============================
# def get_current_price(ticker):
#     if not ticker or ticker == "GENERAL": return 0.0
#     try:
#         # ใช้ fast_info หรือ history(period='1d') ก็ได้
#         return yf.Ticker(ticker).fast_info.last_price
#     except:
#         return 0.0

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

    context_str += "\n" + get_macro_context()

    return context_str.strip()

# ============================
# 📈 ฟังก์ชันดึงเทคนิคอล (RSI, SMA) จาก yfinance
# ============================
def _fetch_technical_data(ticker):
    """ดึงราคา/SMA50/RSI ดิบ คืนเป็น dict (ใช้ทั้งทำ string โชว์ และคำนวณ score)"""
    try:
        # ดึงข้อมูลย้อนหลัง 3 เดือน (เพื่อให้คำนวณ SMA50 ได้)
        df = yf.Ticker(ticker).history(period="3mo")

        if len(df) < 50:
            return None

        sma50 = df['Close'].rolling(window=50).mean().iloc[-1]
        current_price = df['Close'].iloc[-1]

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs)).iloc[-1]

        return {"price": current_price, "sma50": sma50, "rsi": rsi}
    except Exception as e:
        print(f"⚠️ Technical Data Error: {e}")
        return None


def get_technical_analysis(ticker):
    """ดึงข้อมูลเทคนิคอลครั้งเดียว คืน (string สำหรับ prompt, score -2..+2 สำหรับ confluence)"""
    if not ticker or ticker == "GENERAL":
        return "N/A", 0

    data = _fetch_technical_data(ticker)
    if not data:
        return "Not enough data", 0

    trend = "BULLISH (Above SMA50)" if data["price"] > data["sma50"] else "BEARISH (Below SMA50)"
    rsi_status = "Overbought (>70)" if data["rsi"] > 70 else "Oversold (<30)" if data["rsi"] < 30 else "Neutral"
    text = f"Price: ${data['price']:.2f} | SMA50: ${data['sma50']:.2f} ({trend}) | RSI(14): {data['rsi']:.1f} ({rsi_status})"

    score = 1 if data["price"] > data["sma50"] else -1
    if data["rsi"] < 30:
        score += 1
    elif data["rsi"] > 70:
        score -= 1

    return text, max(-2, min(2, score))



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
    print(f"🧠 กำลังวิเคราะห์ {source_type} ของ {topic} โดยใช้ [{AI_PROVIDER.upper()}]...")

    confluence = None
    if source_type == "NEWS":
        # ticker คือ topic ตรงๆ จึงคำนวณ confluence score แบบ deterministic ได้ก่อนเรียก AI
        technical_info, technical_score = get_technical_analysis(topic)
        fundamental_info = get_fundamental_context(topic)
        fundamental_score = get_fundamental_signal_score(topic)
        macro_score = get_macro_signal_score()
        news_score = get_news_sentiment_score(content_data)

        confluence = compute_confluence(technical_score, fundamental_score, macro_score, news_score)
    else:
        # TWEET: ยังไม่รู้ ticker ที่แท้จริงจนกว่า AI จะระบุ specific_stock กลับมา
        # จึงคำนวณ confluence แบบ deterministic ก่อนเรียกไม่ได้ ปล่อยให้ AI ประเมินเอง
        technical_info, fundamental_info = "N/A", "N/A"

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
        5. Target Price: realistic price level if the move plays out within the time horizon.
        6. Stop Loss Price: level that invalidates this thesis.
        7. Time Horizon (days): how many days this prediction is expected to play out (1-30).
        8. Summary (Thai): Informal/Social tone.

        Response JSON Format ONLY:
        {{
            "impact_score": <int>,
            "predicted_direction": "UP/DOWN/NEUTRAL",
            "specific_stock": "<Ticker Symbol>",
            "affected_sector": "<Sector>",
            "target_price": <float or null>,
            "stop_loss_price": <float or null>,
            "time_horizon_days": <int>,
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

        [FUNDAMENTALS] (For {topic})
        {fundamental_info}

        [COMPUTED CONFLUENCE SIGNAL] (deterministic, calculated from the data above before you were asked)
        {chr(10).join(confluence['breakdown'])}
        Net Score: {confluence['total']:+d} | Bias: {confluence['direction']} | Agreement: {confluence['confluence_count']}/4 categories

        Task: Analyze news for ticker: {topic}
        [NEWS]
        {json.dumps(content_data)}

        Use the COMPUTED CONFLUENCE SIGNAL above as your primary evidence for direction — it is calculated, not guessed.
        Only override its direction if the [NEWS] content contains a strong, specific reason to disagree (explain why in "reason").
        1. Prediction: UP or DOWN in 24h? (default to the confluence bias unless overridden)
        2. Target Price: realistic price level if the move plays out within the time horizon.
        3. Stop Loss Price: level that invalidates this thesis.
        4. Time Horizon (days): how many days this prediction is expected to play out (1-30).
        5. Summary (Thai): Formal tone.

        Response JSON Format ONLY:
        {{
            "predicted_direction": "UP/DOWN/NEUTRAL",
            "target_price": <float or null>,
            "stop_loss_price": <float or null>,
            "time_horizon_days": <int>,
            "summary_message": "<Thai Summary>",
            "reason": "<Reason>"
        }}
        """
    result = None

    if AI_PROVIDER == "openai":
        result = call_openai(prompt)
    elif AI_PROVIDER == "gemini":
        result = call_gemini(prompt)
    elif AI_PROVIDER == "claude":   # <--- เพิ่มตรงนี้
        result = call_claude(prompt)
    else:
        # Fallback: ถ้าตั้งชื่อผิด ให้ลอง Gemini ก่อน
        result = call_gemini(prompt)

    # ป้องกัน AI ส่ง List กลับมา
    if isinstance(result, list):
        if len(result) > 0: result = result[0]
        else: return None

    if result is None:
        return None

    if confluence is not None:
        # ทับ impact_score ด้วยค่าที่คำนวณ deterministic เสมอ (ไม่พึ่ง AI เดาเอง)
        result["impact_score"] = confluence["strength"]
        result["confluence_count"] = confluence["confluence_count"]
        result.setdefault("predicted_direction", confluence["direction"])

    return result

