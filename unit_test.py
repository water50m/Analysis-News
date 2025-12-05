import unittest
from unittest.mock import patch, MagicMock, mock_open
import json
import sys
import os

# Import ฟังก์ชันจากไฟล์ต่างๆ
# (สมมติว่าไฟล์ services.py, get_news.py, get_social.py อยู่ที่เดียวกัน)
from services import analyze_content, send_line_push
import get_news
import get_social

class TestServices(unittest.TestCase):
    """ทดสอบฟังก์ชันกลางใน services.py"""

    @patch('services.requests.post')
    def test_send_line_push_success(self, mock_post):
        """ทดสอบส่ง LINE สำเร็จ"""
        mock_post.return_value.status_code = 200
        send_line_push("Test Message")
        self.assertTrue(mock_post.called)
        # เช็คว่า URL ถูกต้อง
        self.assertEqual(mock_post.call_args[0][0], "https://api.line.me/v2/bot/message/push")
        print("✅ [Services] send_line_push: ผ่าน")

    @patch('services.genai.GenerativeModel')
    def test_analyze_content_success(self, MockGenerativeModel):
        """ทดสอบ AI วิเคราะห์และตอบ JSON กลับมาได้"""
        # จำลองคำตอบจาก Gemini
        expected_json = {
            "impact_score": 8,
            "summary_message": "Test Summary",
            "reason": "Test Reason"
        }
        mock_model = MockGenerativeModel.return_value
        mock_model.generate_content.return_value.text = json.dumps(expected_json)

        # ลองเรียกใช้งาน
        result = analyze_content("NEWS", "TSLA", [{"title": "test"}])
        
        self.assertEqual(result['impact_score'], 8)
        self.assertEqual(result['summary_message'], "Test Summary")
        print("✅ [Services] analyze_content (Success): ผ่าน")

    @patch('services.genai.GenerativeModel')
    def test_analyze_content_failure(self, MockGenerativeModel):
        """ทดสอบกรณี AI Error (คืนค่า None)"""
        mock_model = MockGenerativeModel.return_value
        # จำลองให้เกิด Exception ตอนเรียก generate_content
        mock_model.generate_content.side_effect = Exception("API Error")

        result = analyze_content("NEWS", "TSLA", [])
        self.assertIsNone(result)
        print("✅ [Services] analyze_content (Failure): ผ่าน")


class TestNewsBot(unittest.TestCase):
    """ทดสอบ get_news.py"""

    @patch('get_news.time.sleep') # ข้ามการ sleep
    @patch('get_news.send_line_push')
    @patch('get_news.analyze_content')
    @patch('get_news.requests.get')
    def test_run_news_high_impact(self, mock_get, mock_analyze, mock_send_line, mock_sleep):
        """ทดสอบดึงข่าว -> คะแนนสูง -> ส่งไลน์"""
        
        # 1. จำลองไฟล์ ticker
        mock_tickers = "TSLA\nAAPL"
        
        # 2. จำลอง API Alpha Vantage Response
        mock_get.return_value.json.return_value = {
            "feed": [{"title": "Big News"}]
        }
        
        # 3. จำลอง AI ให้คะแนน 8 (สูงกว่า Threshold 5)
        mock_analyze.return_value = {
            "impact_score": 8,
            "summary_message": "Hot News",
            "reason": "Growth"
        }

        # 4. รันฟังก์ชัน (Mock การเปิดไฟล์)
        with patch("builtins.open", mock_open(read_data=mock_tickers)):
            get_news.run_news_bot()

        # 5. ตรวจสอบว่ามีการส่งไลน์
        self.assertTrue(mock_send_line.called)
        print("✅ [NewsBot] Run Flow (High Impact): ผ่าน")

    @patch('get_news.time.sleep')
    @patch('get_news.send_line_push')
    @patch('get_news.analyze_content')
    @patch('get_news.requests.get')
    def test_run_news_low_impact(self, mock_get, mock_analyze, mock_send_line, mock_sleep):
        """ทดสอบดึงข่าว -> คะแนนต่ำ -> ไม่ส่งไลน์"""
        
        mock_get.return_value.json.return_value = {"feed": [{"title": "Small News"}]}
        
        # คะแนน 3 (ต่ำกว่า Threshold)
        mock_analyze.return_value = {"impact_score": 3, "summary_message": "...", "reason": "..."}

        with patch("builtins.open", mock_open(read_data="TSLA")):
            get_news.run_news_bot()

        # ต้องไม่ส่งไลน์
        mock_send_line.assert_not_called()
        print("✅ [NewsBot] Run Flow (Low Impact): ผ่าน")


class TestSocialBot(unittest.TestCase):
    """ทดสอบ get_social.py"""

    @patch('get_social.time.sleep')
    @patch('get_social.send_line_push')
    @patch('get_social.analyze_content')
    @patch('get_social.requests.get')
    def test_run_social_flow(self, mock_get, mock_analyze, mock_send_line, mock_sleep):
        """ทดสอบดึงทวีต -> คะแนนสูง -> ส่งไลน์"""
        
        # Setup Token หลอกๆ (เพื่อให้ผ่านเงื่อนไข check token)
        get_social.TWITTER_BEARER_TOKEN = "fake_token"
        
        # จำลอง Twitter API Response
        mock_get.return_value.json.return_value = {
            "data": [{"text": "Tweet 1"}]
        }
        
        # จำลอง AI
        mock_analyze.return_value = {
            "impact_score": 9,
            "summary_message": "Elon Tweeted!",
            "reason": "Market Moving",
            "affected_sector": "Tech",
            "specific_stock": "TSLA"
        }

        # รัน
        get_social.run_social_bot()

        # เช็คว่าส่งไลน์ไหม
        self.assertTrue(mock_send_line.called)
        print("✅ [SocialBot] Run Flow: ผ่าน")


# ==========================================
# Run & Report Logic
# ==========================================
if __name__ == '__main__':
    # โหลด Test ทั้งหมด
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestServices))
    suite.addTests(loader.loadTestsFromTestCase(TestNewsBot))
    suite.addTests(loader.loadTestsFromTestCase(TestSocialBot))

    # รัน Test
    runner = unittest.TextTestRunner(verbosity=0)
    result = runner.run(suite)

    # สรุปผล
    total_run = result.testsRun
    total_failures = len(result.failures)
    total_errors = len(result.errors)
    total_passed = total_run - (total_failures + total_errors)

    print("\n" + "="*45)
    print("📊  สรุปผลการทดสอบ (FULL SUITE REPORT)")
    print("="*45)
    print(f"🟢 ผ่าน (Passed): {total_passed}")
    print(f"🔴 ไม่ผ่าน (Failed): {total_failures}")
    print(f"⚠️ เออเร่อ (Errors): {total_errors}")
    print("-" * 45)
    print(f"🔢 รวมทั้งหมด: {total_run} การทดสอบ")
    print("="*45)

    if not result.wasSuccessful():
        print("\n❌ รายการที่ทดสอบ 'ไม่ผ่าน' มีดังนี้:\n")
        for test_case, traceback_text in result.failures + result.errors:
            print(f"   🛑 {test_case._testMethodName}")
            # print(f"      {traceback_text}") # Uncomment ถ้าอยากดู Error เต็มๆ
    else:
        print("\n✨ สุดยอด! ระบบทำงานถูกต้องครบทุกโมดูลครับ ✨")
    print("="*45)