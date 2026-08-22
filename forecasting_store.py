"""PostgreSQL persistence for the event-driven forecasting system.

JSON is intentionally limited to configuration and flexible evidence payloads.
Snapshots and predictions live in relational tables so their outcomes, forecast
quality and mistakes can be queried over time.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import psycopg2.extras

from db_handler import get_connection, release_connection


FORECASTING_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS forecasting_snapshots (
    id BIGSERIAL PRIMARY KEY,
    captured_at TIMESTAMPTZ NOT NULL,
    ticker TEXT NOT NULL,
    theme TEXT NOT NULL,
    signal_score SMALLINT NOT NULL,
    state TEXT NOT NULL,
    metrics JSONB NOT NULL,
    macro_metrics JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS forecasting_snapshots_ticker_captured_idx
    ON forecasting_snapshots (ticker, captured_at DESC);

CREATE TABLE IF NOT EXISTS forecasting_predictions (
    id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    horizon_days INTEGER NOT NULL CHECK (horizon_days BETWEEN 1 AND 365),
    predicted_direction TEXT NOT NULL CHECK (predicted_direction IN ('UP', 'DOWN', 'NEUTRAL')),
    probability_up NUMERIC(5,4) NOT NULL CHECK (probability_up >= 0 AND probability_up <= 1),
    thesis TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    invalidation TEXT NOT NULL,
    start_price NUMERIC NOT NULL CHECK (start_price > 0),
    target_price NUMERIC,
    stop_loss_price NUMERIC,
    due_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'VERIFIED', 'CANCELLED')),
    actual_price NUMERIC,
    actual_return_pct NUMERIC,
    actual_direction TEXT CHECK (actual_direction IN ('UP', 'DOWN', 'NEUTRAL')),
    direction_correct BOOLEAN,
    brier_score NUMERIC(8,6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS forecasting_predictions_due_idx
    ON forecasting_predictions (status, due_at);

CREATE TABLE IF NOT EXISTS forecasting_errors (
    id BIGSERIAL PRIMARY KEY,
    prediction_id BIGINT NOT NULL REFERENCES forecasting_predictions(id),
    error_type TEXT NOT NULL,
    expected_thesis TEXT NOT NULL,
    actual_outcome TEXT NOT NULL,
    lesson TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS forecasting_errors_prediction_idx
    ON forecasting_errors (prediction_id);
"""


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def init_forecasting_db() -> bool:
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn, conn.cursor() as cur:
            cur.execute(FORECASTING_SCHEMA_SQL)
        return True
    except Exception as exc:
        print(f"⚠️ Forecast DB init failed: {exc}")
        return False
    finally:
        release_connection(conn)


def save_snapshot(captured_at: datetime, ticker: str, theme: str, signal_score: int,
                  state: str, metrics: dict, macro_metrics: dict) -> bool:
    conn = get_connection()
    if not conn:
        return False
    sql = """
        INSERT INTO forecasting_snapshots
            (captured_at, ticker, theme, signal_score, state, metrics, macro_metrics)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    try:
        with conn, conn.cursor() as cur:
            cur.execute(sql, (
                captured_at, ticker, theme, signal_score, state,
                psycopg2.extras.Json(_json_safe(metrics)),
                psycopg2.extras.Json(_json_safe(macro_metrics)),
            ))
        return True
    except Exception as exc:
        print(f"⚠️ Forecast snapshot save failed: {exc}")
        return False
    finally:
        release_connection(conn)


def create_prediction(ticker: str, horizon_days: int, predicted_direction: str,
                      probability_up: float, thesis: str, evidence: list[str],
                      invalidation: str, start_price: float, target_price: float | None = None,
                      stop_loss_price: float | None = None,
                      created_at: datetime | None = None) -> int | None:
    """Create an auditable forecast. AI output must be reviewed before calling this."""
    if predicted_direction not in {"UP", "DOWN", "NEUTRAL"}:
        raise ValueError("predicted_direction must be UP, DOWN or NEUTRAL")
    if not 0 <= probability_up <= 1:
        raise ValueError("probability_up must be between 0 and 1")

    created_at = created_at or datetime.now(timezone.utc)
    conn = get_connection()
    if not conn:
        return None
    sql = """
        INSERT INTO forecasting_predictions
            (ticker, horizon_days, predicted_direction, probability_up, thesis, evidence,
             invalidation, start_price, target_price, stop_loss_price, due_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    try:
        with conn, conn.cursor() as cur:
            cur.execute(sql, (
                ticker, horizon_days, predicted_direction, probability_up, thesis,
                psycopg2.extras.Json(_json_safe(evidence)), invalidation, start_price,
                target_price, stop_loss_price, created_at + timedelta(days=horizon_days),
            ))
            return cur.fetchone()[0]
    finally:
        release_connection(conn)


def get_due_predictions() -> list[dict]:
    conn = get_connection()
    if not conn:
        return []
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM forecasting_predictions WHERE status = 'PENDING' AND due_at <= NOW()")
            return [dict(row) for row in cur.fetchall()]
    finally:
        release_connection(conn)


def verify_prediction(prediction_id: int, actual_price: float, movement_threshold_pct: float = 0.5) -> bool:
    """Close a forecast, calculate calibration (Brier score) and retain a mistake row if wrong."""
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM forecasting_predictions WHERE id = %s FOR UPDATE", (prediction_id,))
            prediction = cur.fetchone()
            if not prediction or prediction["status"] != "PENDING":
                return False

            start_price = float(prediction["start_price"])
            actual_return = ((actual_price / start_price) - 1) * 100
            actual_direction = "UP" if actual_return > movement_threshold_pct else (
                "DOWN" if actual_return < -movement_threshold_pct else "NEUTRAL"
            )
            direction_correct = prediction["predicted_direction"] == actual_direction
            # Brier score evaluates the probability assigned to an upward move.
            brier_score = (float(prediction["probability_up"]) - (1 if actual_direction == "UP" else 0)) ** 2
            cur.execute("""
                UPDATE forecasting_predictions
                SET status = 'VERIFIED', actual_price = %s, actual_return_pct = %s,
                    actual_direction = %s, direction_correct = %s, brier_score = %s, verified_at = NOW()
                WHERE id = %s
            """, (actual_price, actual_return, actual_direction, direction_correct, brier_score, prediction_id))
            if not direction_correct:
                cur.execute("""
                    INSERT INTO forecasting_errors (prediction_id, error_type, expected_thesis, actual_outcome)
                    VALUES (%s, 'DIRECTION', %s, %s)
                """, (
                    prediction_id,
                    prediction["thesis"],
                    f"{prediction['ticker']} moved {actual_return:.2f}% ({actual_direction}) over the forecast horizon.",
                ))
        return True
    except Exception as exc:
        print(f"⚠️ Forecast verification failed: {exc}")
        return False
    finally:
        release_connection(conn)


def get_forecast_statistics() -> dict:
    conn = get_connection()
    if not conn:
        return {"total": 0, "accuracy_pct": None, "mean_brier_score": None, "errors": 0}
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*), AVG(CASE WHEN direction_correct THEN 1.0 ELSE 0.0 END), AVG(brier_score)
                FROM forecasting_predictions WHERE status = 'VERIFIED'
            """)
            total, accuracy, brier = cur.fetchone()
            cur.execute("SELECT COUNT(*) FROM forecasting_errors")
            errors = cur.fetchone()[0]
            return {
                "total": total,
                "accuracy_pct": round(float(accuracy) * 100, 2) if accuracy is not None else None,
                "mean_brier_score": round(float(brier), 4) if brier is not None else None,
                "errors": errors,
            }
    finally:
        release_connection(conn)


def get_latest_watchlist_states() -> list[dict]:
    """Return one latest evidence snapshot per ticker for the LINE dashboard."""
    conn = get_connection()
    if not conn:
        return []
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT ON (ticker)
                    ticker, theme, signal_score, state, captured_at
                FROM forecasting_snapshots
                ORDER BY ticker, captured_at DESC
            """)
            return [dict(row) for row in cur.fetchall()]
    except Exception as exc:
        print(f"⚠️ Forecast state query failed: {exc}")
        return []
    finally:
        release_connection(conn)
