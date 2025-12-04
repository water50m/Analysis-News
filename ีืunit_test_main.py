import unittest
from unittest.mock import patch, MagicMock, mock_open
import json
import sys

# Import ฟังก์ชันทั้งหมดจาก main.py
# ตรวจสอบชื่อไฟล์ให้ตรงกับไฟล์งานจริงของคุณ
from main import (
    get_stock_news, 
    analyze_with_gemini, 
    send_line_push, 
    load_tickers, 
    run_analysis_for_ticker,
    IMPACT_THRESHOLD
)

# ==========================================
# PART 1: Test Unit ย่อย (ฟังก์ชันพื้นฐาน)
# ==========================================
class TestStockBot(unittest.TestCase):

    @patch('main.requests.get')
    def test_get_stock_news_success(self, mock_get):
        """ทดสอบกรณีดึงข่าวสำเร็จ"""
        mock_response = {
            "feed": [
                {"title": "News 1", "summary": "Sum 1", "overall_sentiment_score": 0.5},
                {"title": "News 2", "summary": "Sum 2", "overall_sentiment_score": 0.2}
            ]
        }
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response

        result = get_stock_news("TSLA")
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        print("✅ [Unit] get_stock_news (Success): ผ่าน")

    @patch('main.requests.get')
    def test_get_stock_news_failure(self, mock_get):
        """ทดสอบกรณี API Limit เต็ม"""
        mock_response = {"Information": "Limit reached"}
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response

        result = get_stock_news("TSLA")
        self.assertIsNone(result)
        print("✅ [Unit] get_stock_news (Failure): ผ่าน")

    @patch('main.genai.GenerativeModel')
    def test_analyze_with_gemini_success(self, MockGenerativeModel):
        """ทดสอบ Gemini ตอบ JSON ถูกต้อง"""
        expected_json = {
            "impact_score": 8,
            "summary_message": "Good",
            "reason": "Growth"
        }
        
        mock_instance = MockGenerativeModel.return_value
        mock_instance.generate_content.return_value.text = json.dumps(expected_json)

        result = analyze_with_gemini("TSLA", [{"title": "t"}])
        self.assertEqual(result['impact_score'], 8)
        print("✅ [Unit] analyze_with_gemini (Success): ผ่าน")

    @patch('main.requests.post')
    def test_send_line_push(self, mock_post):
        """ทดสอบการยิง LINE API"""
        mock_post.return_value.status_code = 200
        send_line_push("Test Msg")
        self.assertTrue(mock_post.called)
        print("✅ [Unit] send_line_push: ผ่าน")


# ==========================================
# PART 2: Test ฟังก์ชันใหม่ & Workflow
# ==========================================
class TestNewFunctions(unittest.TestCase):

    def test_load_tickers_success(self):
        """ทดสอบอ่านไฟล์หุ้น"""
        mock_content = "TSLA\n  NVDA  \n\nMETA"
        with patch("builtins.open", mock_open(read_data=mock_content)):
            result = load_tickers("dummy.txt")
        self.assertEqual(result, ["TSLA", "NVDA", "META"])
        print("✅ [Helper] load_tickers: ผ่าน")

    @patch('main.send_line_push')
    @patch('main.analyze_with_gemini')
    @patch('main.get_stock_news')
    def test_run_analysis_high_score(self, mock_get_news, mock_analyze, mock_send_line):
        """ทดสอบ Flow: คะแนนสูง -> ต้องส่งไลน์"""
        mock_get_news.return_value = [{"title": "News"}]
        mock_analyze.return_value = {
            "impact_score": 9, 
            "summary_message": "Urgent", 
            "reason": "..."
        }
        
        run_analysis_for_ticker("TSLA")
        
        mock_send_line.assert_called_once()
        print("✅ [Flow] run_analysis (High Score): ผ่าน (ส่งไลน์ถูกต้อง)")

    @patch('main.send_line_push')
    @patch('main.analyze_with_gemini')
    @patch('main.get_stock_news')
    def test_run_analysis_low_score(self, mock_get_news, mock_analyze, mock_send_line):
        """ทดสอบ Flow: คะแนนต่ำ -> ต้องไม่ส่งไลน์"""
        mock_get_news.return_value = [{"title": "News"}]
        mock_analyze.return_value = {
            "impact_score": 2, 
            "summary_message": "Normal", 
            "reason": "..."
        }
        
        run_analysis_for_ticker("TSLA")
        
        mock_send_line.assert_not_called()
        print("✅ [Flow] run_analysis (Low Score): ผ่าน (ไม่ส่งไลน์ถูกต้อง)")


# ==========================================
# Main Test Execution with Summary
# ==========================================
if __name__ == '__main__':
    # รวม Test ทั้งหมดจากทั้ง 2 Class
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestStockBot))
    suite.addTests(loader.loadTestsFromTestCase(TestNewFunctions))

    # รัน Test
    runner = unittest.TextTestRunner(verbosity=0)
    result = runner.run(suite)

    # สรุปผลสวยๆ
    total_run = result.testsRun
    total_failures = len(result.failures)
    total_errors = len(result.errors)
    total_passed = total_run - (total_failures + total_errors)

    print("\n" + "="*45)
    print("📊  สรุปผลการทดสอบ (FULL TEST REPORT)")
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
    else:
        print("\n✨ สุดยอด! ระบบทำงานถูกต้องสมบูรณ์ครับ ✨")
    print("="*45)