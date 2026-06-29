"""Persistent scheduler สำหรับรันบนเซิร์ฟเวอร์ตัวเอง (แทน GitHub Actions cron)
ข้อดี: cron แม่นยำกว่า + ใช้ DB connection pool ตัวเดียวตลอด (ไม่เปิด-ปิดใหม่ทุกรอบตามที่ CLAUDE.md เตือนไว้)

รัน: python scheduler.py
หยุด: Ctrl+C หรือผ่าน systemd (ดู investor-bot.service)
"""

import time
from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.blocking import BlockingScheduler

from screener import update_target_tickers
from get_news import run_news_bot
from verify_bot import run_verification

NY_TZ = ZoneInfo("America/New_York")

SCAN_INTERVAL_MINUTES = 5
SCREENER_TOP_N = 5


def is_market_hours():
    """เช็คตลาด US เปิดอยู่ไหม (09:30-16:00 ตามเวลา New York จัดการ DST อัตโนมัติ)"""
    now = datetime.now(NY_TZ)
    if now.weekday() >= 5:  # เสาร์-อาทิตย์
        return False
    open_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close_time = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_time <= now <= close_time


def scan_and_analyze_job():
    """งานหลัก: screener คัดหุ้นซิ่ง -> เขียน target_ticker.txt -> วิเคราะห์ลึกต่อทันที"""
    if not is_market_hours():
        print(f"💤 [{datetime.now(NY_TZ)}] ตลาดปิด ข้ามรอบสแกน")
        return

    print(f"\n⏰ [{datetime.now(NY_TZ)}] เริ่มรอบสแกน...")
    movers = update_target_tickers(top_n=SCREENER_TOP_N)

    if movers:
        run_news_bot()
    else:
        print("💤 ไม่มีหุ้นซิ่งผ่านเกณฑ์ ข้ามการวิเคราะห์รอบนี้")


def verify_job():
    """งานตรวจผลคำทำนาย รันวันละครั้ง (เวลาใดก็ได้ที่ตลาดปิดแล้ว)"""
    print(f"\n🕵️ [{datetime.now(NY_TZ)}] เริ่มตรวจผลคำทำนาย...")
    run_verification()


def main():
    scheduler = BlockingScheduler(timezone=NY_TZ)

    scheduler.add_job(
        scan_and_analyze_job,
        "interval",
        minutes=SCAN_INTERVAL_MINUTES,
        id="scan_and_analyze",
        max_instances=1,  # ป้องกันรอบใหม่ทับรอบเก่าที่ยังไม่จบ
        coalesce=True,
    )

    scheduler.add_job(
        verify_job,
        "cron",
        hour=18,  # 18:00 New York = หลังตลาดปิดแน่นอน
        minute=0,
        day_of_week="mon-fri",
        id="verify",
    )

    print("🚀 Scheduler started. กด Ctrl+C เพื่อหยุด")
    print(f"   - Scan & Analyze: ทุก {SCAN_INTERVAL_MINUTES} นาที (เฉพาะช่วงตลาดเปิด 09:30-16:00 ET)")
    print(f"   - Verify: ทุกวันจันทร์-ศุกร์ 18:00 ET")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Scheduler stopped.")


if __name__ == "__main__":
    main()
