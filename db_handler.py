import os
import psycopg2
import psycopg2.extras
import psycopg2.pool
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_USER = os.environ.get("DB_USER")
DB_NAME = os.environ.get("DB_NAME")
DB_PASS = os.environ.get("DB_PASS")

_pool = None


def _get_pool():
    global _pool
    if _pool is None and all([DB_HOST, DB_USER, DB_NAME, DB_PASS]):
        _pool = psycopg2.pool.SimpleConnectionPool(
            1, 10,
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            dbname=DB_NAME,
        )
    return _pool

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    symbol TEXT,
    source_type TEXT,
    news_summary TEXT,
    predicted_direction TEXT,
    confidence_score INTEGER,
    start_price NUMERIC,
    end_price NUMERIC,
    is_correct BOOLEAN,
    status TEXT DEFAULT 'PENDING',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS target_price NUMERIC;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS stop_loss_price NUMERIC;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS time_horizon_days INTEGER;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS confluence_count INTEGER;
"""


def get_connection():
    """ดึง connection จาก pool (ไม่ได้เปิดใหม่ทุกครั้ง) ใช้คู่กับ release_connection() เสมอ"""
    pool = _get_pool()
    if pool is None:
        print("❌ Error: ไม่พบค่า DB_HOST/DB_USER/DB_NAME/DB_PASS")
        return None
    try:
        return pool.getconn()
    except Exception as e:
        print(f"❌ DB Connection Error: {e}")
        return None


def release_connection(conn):
    """คืน connection กลับ pool แทนการปิดทิ้ง (ห้ามเรียก conn.close() ตรงๆ)"""
    if conn is None:
        return
    pool = _get_pool()
    if pool is not None:
        pool.putconn(conn)


def init_db():
    """สร้างตาราง predictions ถ้ายังไม่มี"""
    conn = get_connection()
    if not conn:
        return
    try:
        with conn, conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
        print("✅ DB: predictions table ready")
    except Exception as e:
        print(f"❌ DB Init Error: {e}")
    finally:
        release_connection(conn)


def save_prediction(symbol, source_type, summary, direction, score, current_price,
                     target_price=None, stop_loss_price=None, time_horizon_days=None,
                     confluence_count=None):
    """บันทึกคำทำนายลง Postgres"""
    conn = get_connection()
    if not conn:
        return

    sql = """
        INSERT INTO predictions
            (symbol, source_type, news_summary, predicted_direction, confidence_score, start_price,
             target_price, stop_loss_price, time_horizon_days, confluence_count, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'PENDING')
    """
    try:
        with conn, conn.cursor() as cur:
            cur.execute(sql, (symbol, source_type, summary, direction, score, current_price,
                               target_price, stop_loss_price, time_horizon_days, confluence_count))
        print(f"☁️ DB: Saved {symbol} ({direction})")
    except Exception as e:
        print(f"❌ DB Error: {e}")
    finally:
        release_connection(conn)


def get_due_predictions():
    """ดึงรายการ PENDING ที่ครบ time_horizon_days แล้ว (ไม่เช็คก่อนกรอบเวลาที่ AI กำหนดเอง)
    ถ้าไม่มี time_horizon_days (AI ไม่ได้ตอบมา) ใช้ 1 วันเป็นค่า fallback เดิม"""
    conn = get_connection()
    if not conn:
        return []

    sql = """
        SELECT * FROM predictions
        WHERE status = 'PENDING'
          AND created_at + (COALESCE(time_horizon_days, 1) || ' days')::interval <= NOW()
    """
    try:
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(row) for row in cur.fetchall()]
    except Exception as e:
        print(f"❌ Error fetching due predictions: {e}")
        return []
    finally:
        release_connection(conn)


def update_verification(id, end_price, is_correct):
    """อัปเดตผลสอบ"""
    conn = get_connection()
    if not conn:
        return

    sql = """
        UPDATE predictions
        SET end_price = %s, is_correct = %s, status = 'VERIFIED'
        WHERE id = %s
    """
    try:
        with conn, conn.cursor() as cur:
            cur.execute(sql, (end_price, is_correct, id))
        print(f"☁️ DB: Verified ID {id}")
    except Exception as e:
        print(f"❌ Error updating: {e}")
    finally:
        release_connection(conn)


def get_accuracy_stats():
    """ดึงสถิติความแม่นยำ"""
    conn = get_connection()
    if not conn:
        return 0, 0

    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM predictions WHERE status = 'VERIFIED'")
            total = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM predictions WHERE is_correct = TRUE")
            correct = cur.fetchone()[0]

        return total, correct
    except Exception as e:
        print(f"❌ Error stats: {e}")
        return 0, 0
    finally:
        release_connection(conn)


def get_learning_examples(limit=3):
    """ดึงตัวอย่างที่ทายผิดมาสอน AI"""
    conn = get_connection()
    if not conn:
        return []

    sql = """
        SELECT symbol, news_summary, predicted_direction, start_price, end_price, id
        FROM predictions
        WHERE status = 'VERIFIED' AND is_correct = FALSE
        ORDER BY id DESC
        LIMIT %s
    """
    try:
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (limit,))
            return [dict(row) for row in cur.fetchall()]
    except Exception as e:
        print(f"❌ Error examples: {e}")
        return []
    finally:
        release_connection(conn)


if __name__ == "__main__":
    init_db()
