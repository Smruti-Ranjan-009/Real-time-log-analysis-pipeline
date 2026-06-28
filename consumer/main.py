"""
RTLA — FastAPI Application (Phase 1 + 2)
Phase 1: Kafka consumer → PostgreSQL (log ingestion)
Phase 2: Qdrant + Groq RAG (log intelligence)

Run from rtla/ directory:
    uvicorn consumer.main:app --reload --host 0.0.0.0 --port 8001
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Query, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .database import init_db, get_recent_logs, get_stats, get_error_logs
from .kafka_consumer import start_consumer, stop_consumer, get_counters

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("rtla.api")


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== RTLA Phase 2 starting up ===")
    init_db()
    start_consumer()
    yield
    logger.info("=== RTLA Phase 2 shutting down ===")
    stop_consumer()


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="RTLA — Real-Time Log Intelligence",
    description=(
        "Real-time log analysis pipeline with LLM-powered querying.\n\n"
        "**Phase 1:** Kafka → FastAPI → PostgreSQL\n\n"
        "**Phase 2:** Qdrant vector store + Groq Llama 3 RAG\n\n"
        "Latency budget target: sub-500 ms end-to-end."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response models ───────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str
    level_filter: str = None   # optional: ERROR | WARN | INFO | DEBUG

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"query": "What caused the payment service errors?"},
                {"query": "Which service has the most circuit breaker trips?", "level_filter": "ERROR"},
                {"query": "Show me all slow query warnings", "level_filter": "WARN"},
            ]
        }
    }


# ── Phase 1 endpoints ─────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    return {
        "status":    "ok",
        "version":   "2.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/consumer/stats", tags=["System"])
def consumer_stats():
    """In-memory counters from the Kafka consumer thread."""
    return get_counters()


@app.get("/logs", tags=["Logs"])
def get_logs(
    limit: int = Query(50, ge=1, le=500),
    level: str = Query(None, description="ERROR | WARN | INFO | DEBUG"),
):
    if level and level.upper() not in {"ERROR", "WARN", "INFO", "DEBUG", "UNKNOWN"}:
        raise HTTPException(status_code=400, detail=f"Invalid level: {level}")
    logs = get_recent_logs(limit=limit, level=level)
    return {"count": len(logs), "filter": level, "logs": logs}


@app.get("/logs/errors", tags=["Logs"])
def get_errors(limit: int = Query(20, ge=1, le=200)):
    return {"logs": get_error_logs(limit=limit)}


@app.get("/stats", tags=["Pipeline"])
def pipeline_stats():
    stats = get_stats()
    if not stats:
        return {"message": "No data yet — start the log generator."}
    return stats


# ── Phase 2 endpoints ─────────────────────────────────────────────────────────

@app.post("/index", tags=["Intelligence"])
def index_logs(
    background_tasks: BackgroundTasks,
    max_logs: int = Query(1000, ge=1, le=5000, description="Max logs to index per call"),
):
    """
    Embed recent log entries and upsert them into Qdrant.
    Runs synchronously (returns when indexing is complete).
    For large datasets, increase max_logs.
    """
    from intelligence.indexer import index_logs as _index
    result = _index(max_logs=max_logs)
    return result


@app.get("/index/status", tags=["Intelligence"])
def index_status():
    """How many logs are currently indexed in Qdrant."""
    from intelligence.indexer import get_index_status
    return get_index_status()


@app.post("/query", tags=["Intelligence"])
def query_logs(request: QueryRequest):
    """
    Natural language query over indexed logs via RAG.

    **Examples:**
    - "What caused the payment service errors?"
    - "Which services are hitting circuit breakers?"
    - "Show me all slow database queries in the last run"
    - "What's the most common error pattern?"

    Returns answer + source log entries + latency breakdown.
    Automatically degrades gracefully if Groq or Qdrant is unavailable.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    from intelligence.rag import query_logs as _query
    return _query(user_query=request.query, level_filter=request.level_filter)
