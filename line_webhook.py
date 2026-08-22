"""รับคำสั่งจาก LINE (webhook) — คนละทางกับ services.send_line_push() ที่ส่งออกอย่างเดียว
รันเป็น service แยกจาก scheduler.py เพราะ scheduler ใช้ BlockingScheduler ครองเธรดหลักอยู่แล้ว

Endpoint: POST /callback (ให้ Cloudflare Tunnel แมป public hostname มาที่ port นี้)
ความปลอดภัย:
  1. ตรวจ X-Line-Signature (HMAC-SHA256 ด้วย LINE_CHANNEL_SECRET) กันคนปลอมยิง request เข้ามา
  2. รับคำสั่งเฉพาะจาก user ID ที่อยู่ใน ALLOWED_LINE_USER_IDS เท่านั้น (กันคนอื่นในกลุ่มสั่งงานระบบ)
"""

import os
import base64
import hashlib
import hmac
import json

import pandas as pd
from flask import Flask, request, abort
from dotenv import load_dotenv

from services import send_line_push, IMPACT_THRESHOLD
from db_handler import get_accuracy_stats, get_due_predictions
from forecasting_store import get_forecast_statistics, get_latest_watchlist_states
from screener import update_target_tickers
from get_news import run_news_bot
from event_tracker import run as run_event_tracker

load_dotenv()

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
ALLOWED_LINE_USER_IDS = {
    uid.strip() for uid in os.getenv("ALLOWED_LINE_USER_IDS", "").split(",") if uid.strip()
}
# Keep certificate validation on by default.  Some managed networks inject a
# private TLS certificate; only that deployment should explicitly opt out.
LINE_TLS_VERIFY = os.getenv("LINE_TLS_VERIFY", "true").strip().lower() not in {"0", "false", "no"}

app = Flask(__name__)


def verify_signature(body, signature):
    if not LINE_CHANNEL_SECRET or not signature:
        return False
    expected = base64.b64encode(
        hmac.new(LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(expected, signature)


def reply(reply_token, text):
    import requests
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]}
    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=10,
            verify=LINE_TLS_VERIFY,
        )
        if not response.ok:
            print(f"❌ LINE Reply Error: HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ LINE Reply Error: {e}")


def format_immediate_analysis(snapshot: pd.DataFrame) -> str:
    """Turn a fresh 20-stock snapshot into a short, evidence-only LINE reply."""
    usable = snapshot[~snapshot["state"].astype(str).str.contains("DATA ERROR", na=False)].copy()
    if usable.empty:
        return "⚠️ ดึงข้อมูลราคาไม่สำเร็จในรอบนี้ ลอง /analyze อีกครั้งภายหลัง"

    positive = usable[usable["signal_score"] >= 2].sort_values(
        ["signal_score", "return_5d_pct"], ascending=False
    )
    caution = usable[usable["signal_score"] <= -2].sort_values(
        ["signal_score", "return_5d_pct"]
    )
    mixed_count = len(usable) - len(positive) - len(caution)

    def describe(row):
        state = str(row["state"]).split(":", 1)[0]
        return (
            f"{row['ticker']} {row['return_5d_pct']:+.1f}% "
            f"(RSI {row['rsi14']}, {state})"
        )

    lines = ["🔎 วิเคราะห์ทันที — ราคาและสัญญาณ 20 หุ้น"]
    if not positive.empty:
        lines.append("\n✅ เฝ้าดูเชิงบวก")
        lines.extend(describe(row) for _, row in positive.head(5).iterrows())
    else:
        lines.append("\n✅ ยังไม่มีหุ้นที่คะแนนบวกเด่น (≥ +2)")

    if not caution.empty:
        lines.append("\n⚠️ ระวัง")
        lines.extend(describe(row) for _, row in caution.head(5).iterrows())
    else:
        lines.append("\n⚠️ ยังไม่มีหุ้นที่คะแนนลบเด่น (≤ -2)")

    lines.append(f"\n↔️ สัญญาณผสม: {mixed_count} หุ้น")
    lines.append("เป็นสัญญาณวิจัย ไม่ใช่คำสั่งซื้อขาย | /watchlist ดูครบทุกตัว")
    return "\n".join(lines)


def handle_command(text, reply_token):
    text = text.strip().lower()

    if text == "/scan":
        reply(reply_token, "🔍 กำลังสแกนหุ้นซิ่ง รอแป๊บนึง...")
        movers = update_target_tickers()
        if movers:
            run_news_bot()
            send_line_push(f"✅ สแกนเสร็จแล้ว เจอ {len(movers)} ตัว: {', '.join(movers)}")
        else:
            send_line_push("💤 สแกนเสร็จแล้ว ไม่มีหุ้นซิ่งผ่านเกณฑ์ตอนนี้")

    elif text == "/status":
        total, correct = get_accuracy_stats()
        acc = (correct / total * 100) if total > 0 else 0
        pending = len(get_due_predictions())
        forecast_stats = get_forecast_statistics()
        reply(reply_token,
              f"📊 บอทข่าวเดิม: {acc:.1f}% ({correct}/{total})\n"
              f"⏳ รอตรวจบอทข่าว: {pending} รายการ\n"
              f"📈 Watchlist forecast: {forecast_stats['total']} รายการที่ตรวจแล้ว\n"
              f"🎯 Impact Threshold: {IMPACT_THRESHOLD}\n"
              "พิมพ์ /watchlist เพื่อดู 20 หุ้นล่าสุด")

    elif text == "/watchlist":
        states = get_latest_watchlist_states()
        if not states:
            reply(reply_token, "⚠️ ยังไม่มี snapshot watchlist หรือเชื่อมต่อ Forecast DB ไม่ได้")
            return

        lines = ["📈 Fundamental Watchlist ล่าสุด"]
        for item in states:
            state = item["state"].split(":", 1)[0]
            lines.append(f"{item['ticker']} [{item['theme']}] score {item['signal_score']:+d} — {state}")
        lines.append("\nคำอธิบาย: เป็นสถานะหลักฐาน ไม่ใช่คำสั่งซื้อขาย")
        reply(reply_token, "\n".join(lines))

    elif text == "/analyze":
        try:
            snapshot = run_event_tracker()
            reply(reply_token, format_immediate_analysis(snapshot))
        except Exception as exc:
            print(f"❌ Immediate analysis error: {exc}")
            reply(reply_token, "⚠️ วิเคราะห์ไม่สำเร็จในรอบนี้ ลอง /analyze อีกครั้งภายหลัง")

    elif text == "/test":
        reply(reply_token, "✅ LINE webhook ทำงานแล้ว — พิมพ์ /watchlist หรือ /status ได้")

    elif text == "/help":
        reply(reply_token,
              "คำสั่งที่ใช้ได้:\n"
              "/scan - สแกนหุ้นซิ่งทันที + วิเคราะห์\n"
              "/status - เช็คสถานะและสถิติ\n"
              "/watchlist - ดูสัญญาณล่าสุดของ 20 หุ้น\n"
              "/analyze - ดึงราคาและวิเคราะห์สัญญาณ 20 หุ้นทันที\n"
              "/test - ทดสอบการเชื่อมต่อ LINE\n"
              "/help - แสดงคำสั่งทั้งหมด")

    else:
        reply(reply_token, f"❓ ไม่รู้จักคำสั่ง '{text}' พิมพ์ /help เพื่อดูคำสั่งที่ใช้ได้")


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data()

    if not verify_signature(body, signature):
        abort(403)

    events = json.loads(body).get("events", [])
    for event in events:
        if event.get("type") != "message" or event.get("message", {}).get("type") != "text":
            continue

        sender_id = event.get("source", {}).get("userId")
        reply_token = event.get("replyToken")
        text = event["message"]["text"]

        if ALLOWED_LINE_USER_IDS and sender_id not in ALLOWED_LINE_USER_IDS:
            print(f"🚫 Unauthorized LINE command from userId={sender_id}: {text}")
            continue

        if not ALLOWED_LINE_USER_IDS:
            # ยังไม่ตั้ง whitelist ไว้ — log userId ไว้ให้คุณเอาไปใส่ ALLOWED_LINE_USER_IDS
            print(f"ℹ️ LINE message from userId={sender_id} (ALLOWED_LINE_USER_IDS ยังไม่ตั้งค่า): {text}")

        handle_command(text, reply_token)

    return "OK", 200


@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
