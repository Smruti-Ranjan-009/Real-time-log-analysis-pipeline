"""
RTLA Phase 2 — Indexer
Pulls log entries from PostgreSQL that haven't been indexed yet,
embeds them in batches, and upserts to Qdrant.

Tracks progress via an in-memory cursor (_last_indexed_id).
On restart it re-indexes from 0 — Qdrant upsert is idempotent so this is safe.
"""

import logging
import os
import time

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from .embedder import embed
from .vector_store import ensure_collection, upsert_logs, count

load_dotenv()
logger = logging.getLogger("rtla.indexer")

BATCH_SIZE = 64   # logs per embedding batch

_last_indexed_id: int = 0   # cursor — highest PostgreSQL id indexed so far


# ── DB helper (standalone — avoids circular import with consumer.database) ────

def _fetch_logs(after_id: int, limit: int) -> list[dict]:
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "rtla"),
        user=os.getenv("POSTGRES_USER", "rtla_user"),
        password=os.getenv("POSTGRES_PASSWORD", "rtla_pass"),
        connect_timeout=5,
    )
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, timestamp, level, service, message
                FROM log_entries
                WHERE id > %s
                ORDER BY id ASC
                LIMIT %s
                """,
                (after_id, limit),
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ── Public API ────────────────────────────────────────────────────────────────

def index_logs(max_logs: int = 1000) -> dict:
    """
    Index up to `max_logs` new entries from PostgreSQL into Qdrant.
    Returns a stats dict.
    """
    global _last_indexed_id

    ensure_collection()

    total_indexed = 0
    t0 = time.perf_counter()

    while total_indexed < max_logs:
        batch = _fetch_logs(after_id=_last_indexed_id, limit=BATCH_SIZE)
        if not batch:
            break   # nothing new to index

        # Text to embed: "LEVEL service: message"
        texts = [
            f"{r['level']} {r['service']}: {r['message']}"
            for r in batch
        ]

        vectors = embed(texts)

        points = [
            {
                "id":     row["id"],
                "vector": vec,
                "payload": {
                    "level":     row["level"],
                    "service":   row["service"],
                    "message":   row["message"],
                    "timestamp": str(row["timestamp"]),
                },
            }
            for row, vec in zip(batch, vectors)
        ]

        upsert_logs(points)

        _last_indexed_id = batch[-1]["id"]
        total_indexed += len(batch)
        logger.info(
            f"Indexed {len(batch)} logs (batch). "
            f"Cursor now at id={_last_indexed_id}. "
            f"Total this run: {total_indexed}"
        )

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

    return {
        "indexed_this_run": total_indexed,
        "last_id":          _last_indexed_id,
        "total_in_qdrant":  count(),
        "duration_ms":      elapsed_ms,
    }


def get_index_status() -> dict:
    try:
        total = count()
        return {
            "total_indexed":   total,
            "last_indexed_id": _last_indexed_id,
            "qdrant_available": True,
        }
    except Exception as e:
        return {
            "total_indexed":    0,
            "last_indexed_id":  _last_indexed_id,
            "qdrant_available": False,
            "error":            str(e),
        }
