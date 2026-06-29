# verify_bot.py
import requests
from services import send_line_push, get_current_price, ALPHA_VANTAGE_API_KEY
from db_handler import get_due_predictions, update_verification, get_accuracy_stats

def run_verification():
    print("🕵️‍♂️ เริ่มตรวจสอบผลการทำนายของ AI (เฉพาะที่ครบ time_horizon_days แล้ว)...")

    pending_list = get_due_predictions()

    if not pending_list:
        print("✅ ไม่มีรายการที่ครบกรอบเวลาให้ตรวจตอนนี้")
        return

    verified_count = 0
    
    for item in pending_list:
        ticker = item['symbol']
        start_price = item['start_price']
        predicted = item['predicted_direction']
        
        # 1. เช็คราคาปัจจุบัน (End Price)
        end_price = get_current_price(ticker)
        
        if end_price == 0:
            print(f"⚠️ ดึงราคา {ticker} ไม่ได้ ข้ามไปก่อน")
            continue
        

        # 2. ตรวจคำตอบ (Logic ง่ายๆ)

        # คำนวณ % การเปลี่ยนแปลง
        percent_change = ((end_price - start_price) / start_price) * 100

        actual_direction = "NEUTRAL"
        
        # ต้องขึ้น/ลง เกิน 0.5% ถึงจะนับว่าเป็นเทรนด์ (กรอง Noise)
        if percent_change > 0.5:
            actual_direction = "UP"
        elif percent_change < -0.5:
            actual_direction = "DOWN"
        else:
            actual_direction = "NEUTRAL" # ถือว่าราคานิ่งๆ
            
        # AI ทายถูกไหม?
        is_correct = (predicted == actual_direction)
        
        # 3. อัปเดตลง DB
        update_verification(item['id'], end_price, is_correct)
        
        # 4. (Optional) แจ้งเตือนถ้ารู้ผลแล้ว
        status_icon = "✅ แม่นยำ!" if is_correct else "❌ ผิดพลาด"
        print(f"ผล {ticker}: ทาย {predicted} -> ออก {actual_direction} ({status_icon})")
        
        # ส่งรายงานสรุปเข้า LINE (เฉพาะรายการที่เพิ่งตรวจเสร็จ)
        msg = f"📝 ผลการเรียนรู้ AI ({ticker})\n"
        msg += f"ตอนทาย: ${start_price} -> ตอนนี้: ${end_price}\n"
        msg += f"ทายว่า: {predicted} | ผลจริง: {actual_direction}\n"
        msg += f"สรุป: {status_icon}"
        send_line_push(msg)
        
        verified_count += 1

    # 5. สรุปภาพรวม
    total, correct = get_accuracy_stats()
    if total > 0:
        accuracy = (correct / total) * 100
        print(f"📊 ความแม่นยำสะสม: {accuracy:.2f}% ({correct}/{total})")

if __name__ == "__main__":
    run_verification()