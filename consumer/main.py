"""
consumer/main.py  (Phase 3 — instrumented)
───────────────────────────────────────────
New in Phase 3:
  • GET /metrics  — Prometheus scrape endpoint (text/plain; version=0.0.4)
  • GET /slo      — JSON SLO status snapshot (human-readable dashboard helper)
  • POST /ingest  — measures the ingest stage (50 ms budget)
  • All existing endpoints unchanged
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from consumer.database import (
    get_recent_logs,
    get_error_logs,
    get_stats,
    init_db,
)
from consumer.kafka_consumer import RtlaKafkaConsumer
from monitoring import (
    logs_ingested_total,
    slo_violations_total,
    stage_latency,
    SLO_BUDGETS_S,
)
from monitoring.slo import measure_stage_async

log = logging.getLogger("rtla.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")

# ── Kafka consumer singleton ───────────────────────────────────────────────
consumer = RtlaKafkaConsumer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    consumer.start()
    yield
    consumer.stop()


app = FastAPI(
    title="RTLA — Real-Time Log Intelligence System",
    version="0.3.0",
    description="Phase 3: Prometheus + Grafana SLO instrumentation",
    lifespan=lifespan,
)


# ══════════════════════════════════════════════════════════════════════════
# Prometheus scrape endpoint
# ══════════════════════════════════════════════════════════════════════════

@app.get("/metrics", include_in_schema=False)
async def metrics():
    """
    Prometheus scrape target.
    Add to prometheus.yml:
        - targets: ["host.docker.internal:8001"]
    """
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


# ══════════════════════════════════════════════════════════════════════════
# SLO status helper
# ══════════════════════════════════════════════════════════════════════════

@app.get("/slo")
async def slo_status():
    """
    Returns per-stage SLO budgets and live violation counts.
    Useful for dashboards and alerting sanity-checks.
    """
    violations = {}
    for stage in SLO_BUDGETS_S:
        try:
            val = slo_violations_total.labels(stage=stage)._value.get()
        except Exception:
            val = 0
        violations[stage] = int(val)

    return {
        "budgets_ms": {s: round(v * 1000) for s, v in SLO_BUDGETS_S.items()},
        "violations_total": violations,
    }


# ══════════════════════════════════════════════════════════════════════════
# Existing Phase 1 / 2 endpoints (unchanged logic, ingest stage added)
# ══════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    try:
        get_stats()
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}


@app.get("/logs")
async def list_logs(
    limit: int = Query(50, ge=1, le=500),
    level: str = Query(None),
    service: str = Query(None),
):
    return {"logs": get_recent_logs(limit=limit, level=level)}


@app.get("/logs/errors")
async def error_logs(limit: int = Query(50, ge=1, le=500)):
    return {"logs": get_error_logs(limit=limit)}


@app.get("/stats")
async def pipeline_stats():
    return get_stats()


@app.get("/consumer/stats")
async def consumer_stats():
    return consumer.get_stats()


# ── Optional: direct HTTP ingest endpoint (measures ingest stage) ──────────
@app.post("/ingest")
async def ingest_log(request: Request):
    """
    Accept a raw log line via HTTP POST.
    Measures the ingest stage (50 ms budget).
    The main ingest path is Kafka; this is a convenience fallback.
    """
    body = await request.body()
    raw = body.decode("utf-8", errors="replace").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty body")

    async with measure_stage_async("ingest"):
        # Re-use the consumer's message handler directly
        from consumer.parser import parse_log
        from consumer.database import insert_log

        parsed = parse_log(raw)
        if parsed is None:
            raise HTTPException(status_code=422, detail="Could not parse log line")

        level = parsed.get("level", "UNKNOWN").upper()
        logs_ingested_total.labels(level=level).inc()
        insert_log(parsed)

    return {"status": "ingested", "level": level}