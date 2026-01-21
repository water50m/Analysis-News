# 🤖 AI Stock Analyst & Trader Apprentice (เด็กฝึกงานเทรด AI)

ระบบบอทอัจฉริยะที่ทำหน้าที่เป็น **ผู้ช่วยนักวิเคราะห์ส่วนตัว**
โดยใช้ AI อ่านข่าวและโซเชียล (Twitter/X) เพื่อทำนายทิศทางราคาหุ้น (**UP / DOWN**)
พร้อมระบบ **Feedback Loop** ที่ทำให้ AI เรียนรู้จากความผิดพลาดและเก่งขึ้นทุกวัน

> ⚠️ โปรเจกต์นี้เพื่อการศึกษา ไม่ใช่คำแนะนำทางการเงิน

---

## ✨ ฟีเจอร์หลัก (Key Features)

- 🧠 **Smart Analysis with Feedback Loop**  
  AI จะได้รับสถิติความแม่นยำย้อนหลังและกรณีที่เคยทายผิดไปพร้อมกับ Prompt  
  เพื่อปรับปรุงการวิเคราะห์แบบ In-Context Learning

- 📰 **News Bot**  
  วิเคราะห์ข่าวหุ้นรายตัวจาก Alpha Vantage (แนะนำรันวันละครั้ง)

- 🐦 **Social Bot**  
  วิเคราะห์ทวีตจากบุคคลสำคัญ เช่น Elon Musk, Fed, SEC  
  พร้อมระบุหุ้นที่ได้รับผลกระทบโดยอัตโนมัติ (รันทุกชั่วโมง)

- 🔮 **Prediction & Verification**  
  ทำนายทิศทางราคา (UP / DOWN) และมีบอทตรวจคำตอบจากราคาจริงในตลาด

- ☁️ **Cloud Database (Supabase)**  
  เก็บประวัติการทำนายทั้งหมดบน PostgreSQL  
  รองรับการรันผ่าน GitHub Actions โดยข้อมูลไม่หาย

- 📱 **LINE Real-time Alert**  
  แจ้งเตือนเข้า LINE Group พร้อมสรุปภาษาไทยและเหตุผลประกอบ

---

## 📂 โครงสร้างโปรเจกต์ (Project Structure)

```text
my_stock_bot/
├── main_news.py        # บอทวิเคราะห์ข่าว
├── main_social.py      # บอทวิเคราะห์โซเชียล
├── verify_bot.py       # บอทตรวจผลการทำนาย
├── services.py         # Logic กลาง (AI, LINE, ราคา)
├── db_handler.py       # จัดการ Supabase
├── tests/              # Unit & Integration Tests
│   ├── test_full_system.py
│   └── ...
├── .github/workflows/  # GitHub Actions
├── .env                # เก็บ API Keys (ห้ามอัปโหลด)
├── target_ticker.txt   # รายชื่อหุ้นเป้าหมาย
└── requirements.txt    # รายชื่อ Library

🚀 การติดตั้ง (Installation)
1. ติดตั้ง Library
pip install -r requirements.txt


💡 ถ้า copy คำสั่งนี้ไป จะไม่มีคำว่า bash ติดไปแน่นอน

2. ตั้งค่าไฟล์ .env

สร้างไฟล์ .env แล้วใส่ค่าดังนี้

# Financial Data
ALPHA_VANTAGE_API_KEY=your_key

# AI Engine
AI_PROVIDER=gemini
GEMINI_API_KEY=your_key

# Social Data (ถ้าไม่มีจะเข้า Demo Mode)
TWITTER_BEARER_TOKEN=your_token

# Notification
LINE_CHANNEL_ACCESS_TOKEN=your_line_token
LINE_GROUP_ID=Cxxxxxxxxxxxxxxxxxxxxxxx

# Database (Supabase)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_service_role_key


⚠️ สำคัญ:
SUPABASE_KEY ต้องเป็น Service Role Key เท่านั้น

3. ตั้งค่ารายชื่อหุ้น

แก้ไขไฟล์ target_ticker.txt

TSLA
NVDA
AAPL
BTC

🎮 การใช้งาน (Usage)
📰 รันบอทข่าว
python main_news.py


แนะนำรันวันละครั้ง (ช่วงเช้า)

🐦 รันบอทโซเชียล
python main_social.py


แนะนำรันทุก 1–2 ชั่วโมง

👩‍🏫 รันระบบตรวจผลการทำนาย
python verify_bot.py


ระบบจะ:

ดึงรายการที่ยังไม่ตรวจจาก Supabase

เช็คราคาตลาดจริง

อัปเดตผลถูก/ผิด

แจ้งผลเข้า LINE

🧪 การทดสอบระบบ (Testing)

รันทดสอบทั้งหมด

python -m unittest discover tests


หรือทดสอบทั้งระบบ

python tests/test_full_system.py

🤖 Automation (GitHub Actions)

รองรับการรันอัตโนมัติ:

bot_news.yml → รันทุกวัน 08:00

bot_social.yml → รันทุกชั่วโมง

วิธีตั้งค่า

Push โค้ดขึ้น GitHub

ไปที่ Settings → Secrets and variables → Actions

เพิ่มค่าทั้งหมดจาก .env ลงใน Repository Secrets

🤖 การสลับ AI Model (Multi-Provider Support)
ใช้ Google Gemini (ค่าเริ่มต้น)
AI_PROVIDER=gemini
GEMINI_API_KEY=your_key

ใช้ OpenAI (GPT-4 / GPT-3.5)
AI_PROVIDER=openai
OPENAI_API_KEY=sk-xxxx

ใช้ DeepSeek (ผ่าน OpenAI Client)
AI_PROVIDER=openai
OPENAI_API_KEY=sk-deepseek
OPENAI_BASE_URL=https://api.deepseek.com

🔧 เพิ่ม AI Provider อื่น (Advanced)

แก้ไขไฟล์ services.py

def call_claude(prompt):
    # เขียนโค้ดเชื่อมต่อ API ที่นี่
    return result


และเพิ่มเงื่อนไขในฟังก์ชัน analyze_content

if AI_PROVIDER == "openai":
    result = call_openai(prompt)
elif AI_PROVIDER == "gemini":
    result = call_gemini(prompt)
elif AI_PROVIDER == "claude":
    result = call_claude(prompt)

📜 Disclaimer

โปรเจกต์นี้จัดทำขึ้นเพื่อการศึกษาและการทดลองด้าน AI เท่านั้น
ไม่ใช่คำแนะนำทางการเงิน ผู้ลงทุนควรใช้วิจารณญาณก่อนตัดสินใจลงทุน