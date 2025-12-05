import unittest
from unittest.mock import patch, MagicMock, call
import sys
import os
import json

# ==========================================
# 🔧 FIX PATH: ให้มองเห็นไฟล์ข้างนอกโฟลเดอร์ tests
# ==========================================
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Import Modules
import services
import db_handler
import verify_bot

class TestServices(unittest.TestCase):
    """ทดสอบ services.py (สมองกลาง)"""

    @patch('services.requests.get')
    def test_get_current_price(self, mock_get):
        """ทดสอบดึงราคาหุ้น"""
        # จำลอง Response จาก Alpha Vantage
        mock_response = {
            "Global Quote": {"05. price": "150.50"}
        }
        mock_get.return_value.json.return_value = mock_response

        price = services.get_current_price("TSLA")
        self.assertEqual(price, 150.50)
        print("✅ [Services] get_current_price: ผ่าน")

    @patch('services.get_learning_examples') # Mock การดึงบทเรียนเก่า
    @patch('services.get_accuracy_stats')   # Mock การดึงสถิติ
    @patch('services.genai.GenerativeModel')
    def test_analyze_content_with_feedback(self, MockModel, mock_stats, mock_examples):
        """ทดสอบ AI พร้อม Feedback Loop (สำคัญ!)"""
        
        # 1. Setup Mock Data
        mock_stats.return_value = (10, 5) # 50% accuracy
        mock_examples.return_value = [
            {"news_summary": "Old News", "predicted_direction": "UP", "end_price": 90}
        ]
        
        # จำลอง AI ตอบกลับมา
        mock_ai_response = {
            "impact_score": 8,
            "predicted_direction": "DOWN",
            "summary_message": "Test",
            "reason": "Test"
        }
        MockModel.return_value.generate_content.return_value.text = json.dumps(mock_ai_response)

        # 2. เรียกใช้งาน
        result = services.analyze_content("NEWS", "TSLA", [{"title": "New News"}])

        # 3. Assertions
        self.assertEqual(result['impact_score'], 8)
        
        # เช็คว่า Prompt ที่ส่งให้ AI มีคำว่า "MISTAKES" อยู่จริงไหม (พิสูจน์ Feedback Loop)
        args, _ = MockModel.return_value.generate_content.call_args
        prompt_sent = args[0]
        self.assertIn("Current Accuracy: 50.0%", prompt_sent)
        self.assertIn("Here are your past MISTAKES", prompt_sent)
        
        print("✅ [Services] analyze_content (with Feedback Loop): ผ่าน")


class TestDBHandler(unittest.TestCase):
    """ทดสอบ db_handler.py (Supabase)"""

    def setUp(self):
        # สร้าง Mock Client ของ Supabase
        self.mock_supabase = MagicMock()
        db_handler.supabase = self.mock_supabase # Inject mock เข้าไปแทนตัวจริง

    def test_save_prediction(self):
        """ทดสอบบันทึกข้อมูล"""
        db_handler.save_prediction("TSLA", "NEWS", "Summary", "UP", 8, 100.0)
        
        # เช็คว่ามีการเรียก insert
        self.mock_supabase.table.assert_called_with("predictions")
        self.mock_supabase.table().insert.assert_called()
        print("✅ [DB Handler] save_prediction: ผ่าน")

    def test_get_learning_examples(self):
        """ทดสอบดึงตัวอย่างผิดพลาด"""
        db_handler.get_learning_examples(limit=3)
        
        # เช็ค logic การ filter
        # table("predictions").select(...).eq("status", "VERIFIED").eq("is_correct", False)
        self.mock_supabase.table().select().eq().eq.assert_called_with("is_correct", False)
        print("✅ [DB Handler] get_learning_examples: ผ่าน")


class TestVerifyBot(unittest.TestCase):
    """ทดสอบ verify_bot.py (ผู้คุมสอบ)"""

    # 👇 1. เพิ่ม Patch ตรงนี้ (Patch 'get_accuracy_stats')
    @patch('verify_bot.get_accuracy_stats') 
    @patch('verify_bot.send_line_push')
    @patch('verify_bot.update_verification')
    @patch('verify_bot.get_current_price')
    @patch('verify_bot.get_pending_predictions')
    # 👇 2. เพิ่ม argument mock_stats ในวงเล็บ (ลำดับต้องตรงกับ patch: ตัวบนสุดอยู่ท้ายสุดของวงเล็บ)
    def test_run_verification_correct_prediction(self, mock_pending, mock_price, mock_update, mock_line, mock_stats):
        """ทดสอบกรณี: AI ทายถูก (ทาย UP, ราคาขึ้นจริง)"""
        
        # 👇 3. กำหนดค่าให้มันคืนกลับมาเป็นตัวเลข (Total=10, Correct=8)
        # เพื่อให้โค้ด if total > 0: ทำงานได้
        mock_stats.return_value = (10, 8) 
        
        # 1. จำลองข้อมูลที่รอตรวจ (Pending)
        mock_pending.return_value = [{
            "id": 1,
            "symbol": "TSLA",
            "start_price": 100.0,
            "predicted_direction": "UP"
        }]
        
        # 2. จำลองราคาปัจจุบัน (ขึ้นเป็น 110)
        mock_price.return_value = 110.0 
        
        # 3. รันการตรวจสอบ
        verify_bot.run_verification()
        
        # 4. ตรวจสอบผลลัพธ์
        mock_update.assert_called_with(1, 110.0, True)
        mock_line.assert_called()
        print("✅ [VerifyBot] Logic ตรวจคำตอบ (ทายถูก): ผ่าน")

    # 👇 ทำเหมือนกันกับฟังก์ชันทดสอบด้านล่าง
    @patch('verify_bot.get_accuracy_stats')
    @patch('verify_bot.send_line_push')
    @patch('verify_bot.update_verification')
    @patch('verify_bot.get_current_price')
    @patch('verify_bot.get_pending_predictions')
    def test_run_verification_wrong_prediction(self, mock_pending, mock_price, mock_update, mock_line, mock_stats):
        """ทดสอบกรณี: AI ทายผิด (ทาย UP, ราคาลง)"""
        
        # กำหนดค่าตัวเลขป้องกัน Error แบบเดียวกัน
        mock_stats.return_value = (10, 5)

        mock_pending.return_value = [{
            "id": 2, "symbol": "AAPL", "start_price": 150.0, "predicted_direction": "UP"
        }]
        
        # ราคาตกลงเหลือ 140
        mock_price.return_value = 140.0 
        
        verify_bot.run_verification()
        
        # update_verification ต้องถูกเรียกด้วย is_correct=False
        mock_update.assert_called_with(2, 140.0, False)
        print("✅ [VerifyBot] Logic ตรวจคำตอบ (ทายผิด): ผ่าน")


if __name__ == '__main__':
    # รัน Test ทั้งหมด
    unittest.main(verbosity=0)