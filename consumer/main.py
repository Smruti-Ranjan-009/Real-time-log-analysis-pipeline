"""
consumer/main.py  (Phase 2 + 3 — RAG + Prometheus instrumentation)
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from consumer.database import get_recent_logs, get_error_logs, get_stats, init_db
from consumer.kafka_consumer import RtlaKafkaConsumer
from monitoring import logs_ingested_total, slo_violations_total, SLO_BUDGETS_S
from monitoring.slo import measure_stage_async

log = logging.getLogger("rtla.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")

consumer = RtlaKafkaConsumer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    consumer.start()
    yield
    consumer.stop()


app = FastAPI(
    title="RTLA — Real-Time Log Intelligence System",
    version="0.4.0",
    description="Phase 2+3: RAG Intelligence + Prometheus SLO instrumentation",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ────────────────────────────────────────────────────────────────────



class QueryRequest(BaseModel):
    query: str
    level_filter: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"query": "What caused the payment service errors?"},
                {"query": "Which services are hitting circuit breakers?"},
            ]
        }
    }


# ── System ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    try:
        get_stats()
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}


@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/slo")
async def slo_status():
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


@app.get("/consumer/stats")
async def consumer_stats():
    return consumer.get_stats()


# ── Logs ──────────────────────────────────────────────────────────────────────

@app.get("/logs")
async def list_logs(
    limit: int = Query(50, ge=1, le=500),
    level: str = Query(None),
):
    return {"logs": get_recent_logs(limit=limit, level=level)}


@app.get("/logs/errors")
async def error_logs(limit: int = Query(50, ge=1, le=500)):
    return {"logs": get_error_logs(limit=limit)}


@app.get("/stats")
async def pipeline_stats():
    return get_stats()


# ── Ingest (Phase 3 HTTP fallback) ────────────────────────────────────────────

@app.post("/ingest")
async def ingest_log(request: Request):
    body = await request.body()
    raw = body.decode("utf-8", errors="replace").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty body")
    async with measure_stage_async("ingest"):
        from consumer.parser import parse_log
        from consumer.database import insert_log
        parsed = parse_log(raw)
        if parsed is None:
            raise HTTPException(status_code=422, detail="Could not parse log line")
        level = parsed.get("level", "UNKNOWN").upper()
        logs_ingested_total.labels(level=level).inc()
        insert_log(parsed)
    return {"status": "ingested", "level": level}


# ── Intelligence (Phase 2) ────────────────────────────────────────────────────

@app.post("/index")
def index_logs(max_logs: int = Query(1000, ge=1, le=5000)):
    """Embed recent log entries and upsert into Qdrant."""
    from intelligence.indexer import index_logs as _index
    return _index(max_logs=max_logs)


@app.get("/index/status")
def index_status():
    """How many logs are currently indexed in Qdrant."""
    from intelligence.indexer import get_index_status
    return get_index_status()


@app.post("/query")
def query_logs(request: QueryRequest):
    """Natural language query over indexed logs via RAG."""
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    from intelligence.rag import query_logs as _query
    return _query(user_query=request.query, level_filter=request.level_filter)