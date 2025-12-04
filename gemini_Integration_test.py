import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

print("🔍 กำลังค้นหาโมเดลที่ใช้ได้...")
print("--------------------------------")

try:
    for m in genai.list_models():
        # กรองเฉพาะโมเดลที่ใช้คุยได้ (generateContent)
        if 'generateContent' in m.supported_generation_methods:
            print(f"- {m.name}")
except Exception as e:
    print(f"❌ Error: {e}")