"""
RTLA Phase 1 — Database Layer
Thin wrapper around psycopg2 for log_entries table.
Phase 3 will add Prometheus instrumentation here.
"""

import logging
import os
from contextlib import contextmanager
from typing import Any

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("rtla.database")

_DB_CONFIG = {
    "host":     os.getenv("POSTGRES_HOST", "localhost"),
    "port":     int(os.getenv("POSTGRES_PORT", 5432)),
    "dbname":   os.getenv("POSTGRES_DB", "rtla"),
    "user":     os.getenv("POSTGRES_USER", "rtla_user"),
    "password": os.getenv("POSTGRES_PASSWORD", "rtla_pass"),
    "connect_timeout": 5,
}


# ── Connection ────────────────────────────────────────────────────────────────

@contextmanager
def get_db():
    conn = psycopg2.connect(**_DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Init ──────────────────────────────────────────────────────────────────────

def init_db() -> None:
    """
    Create tables and indexes if they don't exist.
    Safe to call on every startup (all statements use IF NOT EXISTS).
    """
    sql = """
        CREATE TABLE IF NOT EXISTS log_entries (
            id               SERIAL PRIMARY KEY,
            timestamp        TIMESTAMPTZ NOT NULL,
            level            VARCHAR(10)  NOT NULL,
            service          VARCHAR(100) NOT NULL,
            message          TEXT NOT NULL,
            raw              TEXT NOT NULL,
            ingested_at      TIMESTAMPTZ DEFAULT NOW(),
            parse_latency_ms FLOAT DEFAULT 0.0
        );

        CREATE INDEX IF NOT EXISTS idx_log_level     ON log_entries(level);
        CREATE INDEX IF NOT EXISTS idx_log_timestamp ON log_entries(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_log_service   ON log_entries(service);

        CREATE OR REPLACE VIEW pipeline_stats AS
        SELECT
            COUNT(*)                                          AS total_1h,
            COUNT(*) FILTER (WHERE level = 'ERROR')           AS errors_1h,
            COUNT(*) FILTER (WHERE level = 'WARN')            AS warnings_1h,
            COUNT(*) FILTER (WHERE level = 'INFO')            AS info_1h,
            COUNT(*) FILTER (WHERE level = 'DEBUG')           AS debug_1h,
            ROUND(AVG(parse_latency_ms)::numeric, 3)          AS avg_parse_ms,
            ROUND(
                PERCENTILE_CONT(0.95) WITHIN GROUP
                (ORDER BY parse_latency_ms)::numeric, 3
            )                                                 AS p95_parse_ms,
            MAX(timestamp)                                    AS last_seen
        FROM log_entries
        WHERE ingested_at > NOW() - INTERVAL '1 hour';
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    logger.info("Database schema ready.")


# ── Write ─────────────────────────────────────────────────────────────────────

def insert_log(entry: dict) -> int:
    """Insert one parsed log entry. Returns the new row id."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO log_entries
                    (timestamp, level, service, message, raw, parse_latency_ms)
                VALUES
                    (%(timestamp)s, %(level)s, %(service)s,
                     %(message)s, %(raw)s, %(parse_latency_ms)s)
                RETURNING id
                """,
                entry,
            )
            return cur.fetchone()[0]


# ── Read ──────────────────────────────────────────────────────────────────────

def get_recent_logs(limit: int = 50, level: str = None) -> list[dict]:
    """Return the most recent log entries, optionally filtered by level."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if level:
                cur.execute(
                    """
                    SELECT * FROM log_entries
                    WHERE level = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                    """,
                    (level.upper(), limit),
                )
            else:
                cur.execute(
                    "SELECT * FROM log_entries ORDER BY timestamp DESC LIMIT %s",
                    (limit,),
                )
            return [dict(r) for r in cur.fetchall()]


def get_stats() -> dict[str, Any]:
    """Return pipeline stats for the last hour from the view."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM pipeline_stats")
            row = cur.fetchone()
            return dict(row) if row else {}


def get_error_logs(limit: int = 20) -> list[dict]:
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM log_entries
                WHERE level = 'ERROR'
                ORDER BY timestamp DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]
