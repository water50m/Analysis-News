import os
import requests
import json
from dotenv import load_dotenv
from services import send_line_push


# โหลดค่าจาก .env
load_dotenv()

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_GROUP_ID = os.getenv("LINE_GROUP_ID")

def test_line_connection():
    print(f"🕵️‍♂️ กำลังตรวจสอบค่า Configuration...")
    
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("❌ Error: ไม่พบ LINE_CHANNEL_ACCESS_TOKEN ใน .env")
        return
    
    if not LINE_GROUP_ID:
        print("❌ Error: ไม่พบ LINE_GROUP_ID ใน .env")
        return

    print(f"✅ Token: พบแล้ว ({LINE_CHANNEL_ACCESS_TOKEN[:10]}...)")
    print(f"✅ Group ID: {LINE_GROUP_ID}")
    print("-" * 30)

    # เตรียมยิง API
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    
    # ข้อความทดสอบ (ส่ง Sticker ด้วยเพื่อความชัวร์)
    payload = {
        "to": LINE_GROUP_ID,
        "messages": [
            {
                "type": "text",
                "text": "🤖 สวัสดีครับ! นี่คือข้อความทดสอบจาก Python Bot \n(ถ้าเห็นข้อความนี้ แสดงว่าระบบพร้อมใช้งานแล้วครับ)"
            },
            {
                "type": "sticker",
                "packageId": "446",
                "stickerId": "1988"
            }
        ]
    }

    print(f"🚀 กำลังส่งข้อความไปยัง LINE...")
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        
        # เช็ค Status Code
        if response.status_code == 200:
            print("\n🎉 สำเร็จ! (Success)")
            print("ข้อความถูกส่งไปที่กลุ่มเรียบร้อยแล้ว กรุณาเช็คในมือถือ")
        else:
            print(f"\n❌ ล้มเหลว (Failed) - Status: {response.status_code}")
            print("👇 รายละเอียด Error จาก LINE:")
            print(response.text) # สำคัญมาก ดูตรงนี้จะรู้ว่าผิดอะไร
            
            # คำแนะนำเบื้องต้นตาม Error Code
            if response.status_code == 400:
                print("💡 คำแนะนำ: เช็คว่า Group ID ถูกต้องไหม หรือ Format ข้อความผิด")
            elif response.status_code == 401:
                print("💡 คำแนะนำ: Token ผิด หรือหมดอายุ")
            elif response.status_code == 404:
                print("💡 คำแนะนำ: บอทอาจจะยังไม่ได้เข้ากลุ่ม หรือ User ID ผิด")

    except Exception as e:
        print(f"\n❌ Error ทางเทคนิค: {e}")

if __name__ == "__main__":
    send_line_push("🤖 สวัสดีครับ! นี่คือข้อความทดสอบจาก Python Bot \n(ถ้าเห็นข้อความนี้ แสดงว่าระบบพร้อมใช้งานแล้วครับ---)")