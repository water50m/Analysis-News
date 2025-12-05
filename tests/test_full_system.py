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

    # เปลี่ยนจาก patch requests เป็น patch yfinance
    @patch('services.yf.Ticker') 
    def test_get_current_price(self, MockTicker):
        """ทดสอบดึงราคาหุ้น (Mock yfinance)"""
        
        # 1. สร้างตัวแทน (Mock Instance)
        mock_instance = MockTicker.return_value
        
        # 2. กำหนดค่าที่ต้องการให้มันตอบกลับมา (150.50)
        # จำลอง structure: Ticker("TSLA").fast_info.last_price
        mock_instance.fast_info.last_price = 150.50

        # 3. เรียกใช้งานฟังก์ชันจริง
        price = services.get_current_price("TSLA")
        
        # 4. ตรวจสอบ
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
        self.assertIn("Your Current Accuracy: 50.0%", prompt_sent)
        self.assertIn("Here are your past MISTAKES", prompt_sent)
        
        print("✅ [Services] analyze_content (with Feedback Loop): ผ่าน")

    def setUp(self):
        # เตรียมคำตอบจำลองจาก AI (Mock Response)
        self.mock_json_response = {
            "impact_score": 8,
            "predicted_direction": "UP",
            "summary_message": "Test Summary",
            "reason": "Test Reason"
        }
    
    # ==================================================
    # 🧪 ทดสอบ 1: ถ้าตั้งค่าเป็น GEMINI (Default)
    # ==================================================
    @patch('services.AI_PROVIDER', 'gemini') # จำลองว่า .env ตั้งเป็น gemini
    @patch('services.call_gemini')           # ดักจับฟังก์ชัน call_gemini
    @patch('services.call_openai')           # ดักจับฟังก์ชัน call_openai
    def test_switch_to_gemini(self, mock_openai, mock_gemini):
        """ทดสอบว่าถ้าเลือก Gemini ระบบต้องเรียก call_gemini เท่านั้น"""
        
        # Setup: ให้ call_gemini คืนค่าได้
        mock_gemini.return_value = self.mock_json_response
        
        # Action: เรียกใช้งานฟังก์ชันหลัก
        services.analyze_content("NEWS", "TSLA", [{"title": "test"}])
        
        # Assert: เช็คผลลัพธ์
        mock_gemini.assert_called_once()  # ✅ ต้องถูกเรียก
        mock_openai.assert_not_called()   # ❌ ต้อง "ไม่" ถูกเรียก
        print("✅ [Switching] Provider='gemini' -> เรียก Gemini ถูกต้อง")

    # ==================================================
    # 🧪 ทดสอบ 2: ถ้าตั้งค่าเป็น OPENAI
    # ==================================================
    @patch('services.AI_PROVIDER', 'openai') # จำลองว่า .env ตั้งเป็น openai
    @patch('services.call_gemini')
    @patch('services.call_openai')
    def test_switch_to_openai(self, mock_openai, mock_gemini):
        """ทดสอบว่าถ้าเลือก OpenAI ระบบต้องเรียก call_openai เท่านั้น"""
        
        mock_openai.return_value = self.mock_json_response
        
        services.analyze_content("NEWS", "TSLA", [{"title": "test"}])
        
        mock_openai.assert_called_once()  # ✅ ต้องถูกเรียก
        mock_gemini.assert_not_called()   # ❌ ต้อง "ไม่" ถูกเรียก
        print("✅ [Switching] Provider='openai' -> เรียก OpenAI ถูกต้อง")

    # ==================================================
    # 🧪 ทดสอบ 3: ทดสอบฟังก์ชันภายใน (Mock Library จริง)
    # ==================================================
    @patch('services.genai.GenerativeModel')
    def test_internal_call_gemini(self, MockGenModel):
        """ทดสอบไส้ในฟังก์ชัน call_gemini ว่าคุยกับ Google library ถูกไหม"""
        
        # Setup Mock ของ Google
        mock_instance = MockGenModel.return_value
        mock_instance.generate_content.return_value.text = json.dumps(self.mock_json_response)
        
        # เรียกใช้ฟังก์ชันย่อยตรงๆ
        result = services.call_gemini("test prompt")
        
        self.assertEqual(result['impact_score'], 8)
        print("✅ [Internal] call_gemini ทำงานถูกต้อง")

    @patch('services.openai_client') # Mock ตัว Client ของ OpenAI
    def test_internal_call_openai(self, mock_client):
        """ทดสอบไส้ในฟังก์ชัน call_openai (กรณีมี client)"""
        
        # ถ้าไม่มี client (เช่นไม่ได้ใส่ key) ฟังก์ชันจะ return None
        if services.openai_client is None:
            # เราแกล้งยัด Mock เข้าไปแทน None เพื่อให้เทสผ่าน
            services.openai_client = mock_client 
        
        # Setup Mock ของ OpenAI Response (ซับซ้อนหน่อยตาม structure จริง)
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = json.dumps(self.mock_json_response)
        mock_client.chat.completions.create.return_value = mock_completion
        
        # เรียกใช้
        result = services.call_openai("test prompt")
        
        self.assertEqual(result['impact_score'], 8)
        print("✅ [Internal] call_openai ทำงานถูกต้อง")    

# ==================================================
    # 🧪 ทดสอบ 4: ถ้าตั้งค่าเป็น CLAUDE (ใหม่ ✨)
    # ==================================================
    @patch('services.AI_PROVIDER', 'claude')
    @patch('services.call_gemini')
    @patch('services.call_openai')
    @patch('services.call_claude')
    def test_switch_to_claude(self, mock_claude, mock_openai, mock_gemini):
        """ทดสอบว่าถ้าเลือก Claude ระบบต้องเรียก call_claude เท่านั้น"""
        
        mock_claude.return_value = self.mock_json_response
        
        services.analyze_content("NEWS", "TSLA", [{"title": "test"}])
        
        mock_claude.assert_called_once()
        mock_gemini.assert_not_called()
        mock_openai.assert_not_called()
        print("✅ [Switching] Provider='claude' -> เรียก Claude ถูกต้อง")

    # ==================================================
    # 🧪 ทดสอบ 5: Internal Gemini Logic
    # ==================================================
    @patch('services.genai.GenerativeModel')
    def test_internal_call_gemini(self, MockGenModel):
        mock_instance = MockGenModel.return_value
        mock_instance.generate_content.return_value.text = json.dumps(self.mock_json_response)
        
        result = services.call_gemini("test prompt")
        self.assertEqual(result['impact_score'], 8)
        print("✅ [Internal] call_gemini ทำงานถูกต้อง")

    # ==================================================
    # 🧪 ทดสอบ 6: Internal Claude Logic (ใหม่ ✨)
    # ==================================================
    # Patch ไปที่ library anthropic ที่ถูก import ใน services.py
    # (ใช้ MagicMock เผื่อเครื่องที่รันยังไม่ได้ลง lib anthropic จริง)
    @patch('services.anthropic.Anthropic') 
    def test_internal_call_claude(self, MockAnthropic):
        """ทดสอบไส้ในฟังก์ชัน call_claude ว่าแกะ JSON ถูกไหม"""
        
        # 1. Setup Mock Client
        mock_client = MockAnthropic.return_value
        
        # 2. Setup Mock Response (Claude return เป็น object ที่ซับซ้อนหน่อย)
        # message.content[0].text
        mock_message_obj = MagicMock()
        # จำลองว่า Claude ตอบมามีข้อความเกริ่นนำนิดหน่อย (Test Logic การตัดคำ)
        raw_text = "Here is the JSON: " + json.dumps(self.mock_json_response)
        mock_message_obj.content = [MagicMock(text=raw_text)]
        
        mock_client.messages.create.return_value = mock_message_obj
        
        # 3. Inject Fake Key (เพื่อให้ผ่านเงื่อนไข if not API_KEY)
        with patch('services.ANTHROPIC_API_KEY', 'sk-fake-key'):
            result = services.call_claude("test prompt")
        
        # 4. Assert
        self.assertIsNotNone(result)
        self.assertEqual(result['impact_score'], 8)
        print("✅ [Internal] call_claude ทำงานถูกต้อง (JSON Parsing)")


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