"""SEC EDGAR (ฟรี 100% ไม่ต้อง key) — เช็คว่าบริษัทยื่นเอกสารที่เกี่ยว 'เพิ่มทุน/dilution' เร็วๆนี้ไหม
เป็นสาเหตุหลักที่หุ้นซิ่งราคาร่วงกะทันหันหลังพุ่งแรง (บริษัทรีบออกหุ้นเพิ่มทุนตอนราคาดี)"""

import requests
from datetime import datetime, timedelta

SEC_HEADERS = {"User-Agent": "InvesterProject research@example.com"}
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

# ฟอร์มที่บ่งบอกความเสี่ยง dilution: S-1/S-3 = จดทะเบียนขายหุ้นใหม่, 424B3/424B5 = prospectus
# supplement ที่มักใช้ตอน "ลงมือขาย" จริงผ่าน ATM offering (สัญญาณเร่งด่วนกว่า S-1/S-3 เฉยๆ)
DILUTIVE_FORMS = {"S-1", "S-3", "424B3", "424B5"}
LOOKBACK_DAYS = 30

_ticker_cik_cache = None


def _load_ticker_cik_map():
    global _ticker_cik_cache
    if _ticker_cik_cache is not None:
        return _ticker_cik_cache

    try:
        res = requests.get(TICKER_MAP_URL, headers=SEC_HEADERS, timeout=15)
        data = res.json()
        _ticker_cik_cache = {v["ticker"].upper(): v["cik_str"] for v in data.values()}
    except Exception as e:
        print(f"❌ SEC Ticker Map Error: {e}")
        _ticker_cik_cache = {}

    return _ticker_cik_cache


def get_recent_dilutive_filings(ticker, days=LOOKBACK_DAYS):
    """คืน list ของ (date, form) ที่ยื่นภายใน N วันล่าสุดที่เข้าข่าย dilution risk"""
    if not ticker or ticker == "GENERAL":
        return []

    cik_map = _load_ticker_cik_map()
    cik = cik_map.get(ticker.upper())
    if not cik:
        return []

    try:
        url = SUBMISSIONS_URL.format(cik=str(cik).zfill(10))
        res = requests.get(url, headers=SEC_HEADERS, timeout=15)
        recent = res.json()["filings"]["recent"]
    except Exception as e:
        print(f"❌ SEC Submissions Error ({ticker}): {e}")
        return []

    cutoff = datetime.now().date() - timedelta(days=days)
    results = []
    for date_str, form in zip(recent["filingDate"], recent["form"]):
        if form in DILUTIVE_FORMS:
            filing_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            if filing_date >= cutoff:
                results.append((date_str, form))

    return results


def get_dilution_risk_score(ticker):
    """คะแนนความเสี่ยง dilution: -2 = มี 424B3/424B5 (กำลังขายจริง) ภายใน 30 วัน (เสี่ยงสูง)
    -1 = มีแค่ S-1/S-3 (จดทะเบียนไว้ ยังไม่ได้ขายจริง) 0 = ไม่พบ"""
    filings = get_recent_dilutive_filings(ticker)
    if not filings:
        return 0

    forms_found = {form for _, form in filings}
    if forms_found & {"424B3", "424B5"}:
        return -2
    return -1


def get_dilution_context(ticker):
    """string สำหรับใส่ใน prompt AI"""
    filings = get_recent_dilutive_filings(ticker)
    if not filings:
        return f"Dilution Risk: No S-1/S-3/424B filings in last {LOOKBACK_DAYS} days"

    filing_list = ", ".join(f"{form} ({date})" for date, form in filings)
    return f"⚠️ Dilution Risk: {filing_list}"
