import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# ตั้งค่า Client
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("❌ Error: ไม่พบ SUPABASE_URL หรือ SUPABASE_KEY")
    supabase = None
else:
    supabase: Client = create_client(url, key)

def save_prediction(symbol, source_type, summary, direction, score, current_price):
    """บันทึกคำทำนายขึ้น Cloud"""
    if not supabase: return

    data = {
        "symbol": symbol,
        "source_type": source_type,
        "news_summary": summary,
        "predicted_direction": direction,
        "confidence_score": score,
        "start_price": current_price,
        "status": "PENDING"
        # prediction_date กับ created_at ทาง Supabase จะใส่เวลาปัจจุบันให้เอง
    }
    
    try:
        supabase.table("predictions").insert(data).execute()
        print(f"☁️ Supabase: Saved {symbol} ({direction})")
    except Exception as e:
        print(f"❌ Supabase Error: {e}")

def get_pending_predictions():
    """ดึงรายการที่รอตรวจ (PENDING)"""
    if not supabase: return []
    
    try:
        # ดึงเฉพาะสถานะ PENDING
        response = supabase.table("predictions").select("*").eq("status", "PENDING").execute()
        return response.data
    except Exception as e:
        print(f"❌ Error fetching pending: {e}")
        return []

def update_verification(id, end_price, is_correct):
    """อัปเดตผลสอบ"""
    if not supabase: return

    data = {
        "end_price": end_price,
        "is_correct": is_correct,
        "status": "VERIFIED"
    }
    
    try:
        supabase.table("predictions").update(data).eq("id", id).execute()
        print(f"☁️ Supabase: Verified ID {id}")
    except Exception as e:
        print(f"❌ Error updating: {e}")

def get_accuracy_stats():
    """ดึงสถิติความแม่นยำ"""
    if not supabase: return 0, 0
    
    try:
        # ดึงจำนวนทั้งหมดที่ตรวจแล้ว
        total_res = supabase.table("predictions").select("id", count="exact").eq("status", "VERIFIED").execute()
        total = total_res.count
        
        # ดึงจำนวนที่ถูก
        correct_res = supabase.table("predictions").select("id", count="exact").eq("is_correct", True).execute()
        correct = correct_res.count
        
        return total, correct
    except Exception as e:
        print(f"❌ Error stats: {e}")
        return 0, 0

def get_learning_examples(limit=3):
    """ดึงตัวอย่างที่ทายผิดมาสอน AI"""
    if not supabase: return []
    
    try:
        # select * from predictions where is_correct = false order by id desc limit 3
        response = supabase.table("predictions")\
            .select("symbol, news_summary, predicted_direction, start_price, end_price")\
            .eq("status", "VERIFIED")\
            .eq("is_correct", False)\
            .order("id", desc=True)\
            .limit(limit)\
            .execute()
            
        return response.data
    except Exception as e:
        print(f"❌ Error examples: {e}")
        return []