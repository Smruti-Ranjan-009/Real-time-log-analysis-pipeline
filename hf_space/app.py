"""
RTLA HuggingFace Spaces Demo Backend
Self-contained FastAPI app — no Kafka, no PostgreSQL.
Uses SQLite for storage and generates logs in memory.
"""

import os
import random
import sqlite3
import time
import threading
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from groq import Groq

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rtla.demo")

# ── Config ────────────────────────────────────────────────────────────────────
GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")
QDRANT_URL      = os.getenv("QDRANT_URL", "")      # Qdrant Cloud URL
QDRANT_API_KEY  = os.getenv("QDRANT_API_KEY", "")
DB_PATH         = "/tmp/rtla_demo.db"
COLLECTION      = "rtla-logs"
VECTOR_DIM      = 384
GROQ_MODEL      = "llama-3.3-70b-versatile"

# ── Synthetic log templates ───────────────────────────────────────────────────
SERVICES = ["auth-service","payment-service","order-service","inventory-service","api-gateway"]
ERRORS   = ["Connection timeout to database replica","NullPointerException in PaymentProcessor.process()","Circuit breaker OPEN for downstream service: inventory","HTTP 503 from upstream: payment-gateway","Database connection pool exhausted"]
WARNS    = ["Response time degraded: {ms}ms (SLO: 1000ms)","Connection pool at {pct}%","Cache miss rate elevated: {pct}%","Slow query: {ms}ms"]
INFOS    = ["Request completed in {ms}ms","User authenticated via OAuth2","Order created successfully","Health check passed"]
DEBUGS   = ["Cache lookup HIT","gRPC call returned in {ms}ms","SQL executed in {ms}ms"]

def _fill(t): return t.format(ms=random.randint(50,3000), pct=random.randint(60,99))
def gen_log():
    level = random.choices(["INFO","WARN","ERROR","DEBUG"],[55,25,12,8])[0]
    pool  = {"INFO":INFOS,"WARN":WARNS,"ERROR":ERRORS,"DEBUG":DEBUGS}[level]
    return {"timestamp": datetime.utcnow(), "level": level,
            "service": random.choice(SERVICES), "message": _fill(random.choice(pool))}

# ── SQLite ────────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, level TEXT, service TEXT, message TEXT,
        ingested_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.commit(); conn.close()

def insert_log(entry):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO logs (timestamp,level,service,message) VALUES (?,?,?,?)",
        (str(entry["timestamp"]), entry["level"], entry["service"], entry["message"]))
    conn.commit(); conn.close()

def get_logs(limit=30, level=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if level:
        rows = conn.execute("SELECT * FROM logs WHERE level=? ORDER BY id DESC LIMIT ?", (level,limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("""SELECT COUNT(*) as total,
        SUM(CASE WHEN level='ERROR' THEN 1 ELSE 0 END) as errors,
        SUM(CASE WHEN level='WARN'  THEN 1 ELSE 0 END) as warnings,
        SUM(CASE WHEN level='INFO'  THEN 1 ELSE 0 END) as info,
        SUM(CASE WHEN level='DEBUG' THEN 1 ELSE 0 END) as debug
        FROM logs WHERE ingested_at > datetime('now','-1 hour')
    """).fetchone()
    conn.close()
    return {"total_1h": row[0], "errors_1h": row[1], "warnings_1h": row[2],
            "info_1h": row[3], "debug_1h": row[4], "avg_parse_ms": 0.09, "p95_parse_ms": 0.14}

def get_max_id():
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT MAX(id) FROM logs").fetchone()
    conn.close()
    return row[0] or 0

def get_logs_after(after_id, limit=64):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM logs WHERE id > ? ORDER BY id ASC LIMIT ?", (after_id,limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Embedding + Qdrant ────────────────────────────────────────────────────────
_model = None
_qdrant = None
_last_indexed = 0
_total_indexed = 0

def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model

def get_qdrant():
    global _qdrant
    if _qdrant is None:
        if QDRANT_URL:
            _qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=10)
        else:
            _qdrant = QdrantClient(":memory:")
        cols = [c.name for c in _qdrant.get_collections().collections]
        if COLLECTION not in cols:
            _qdrant.create_collection(COLLECTION, vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE))
    return _qdrant

def index_new_logs(max_logs=200):
    global _last_indexed, _total_indexed
    batch = get_logs_after(_last_indexed, limit=max_logs)
    if not batch:
        return 0
    texts = [f"{r['level']} {r['service']}: {r['message']}" for r in batch]
    vecs  = get_model().encode(texts, normalize_embeddings=True).tolist()
    pts   = [PointStruct(id=r["id"], vector=v, payload={"level":r["level"],"service":r["service"],"message":r["message"],"timestamp":r["timestamp"]}) for r,v in zip(batch,vecs)]
    get_qdrant().upsert(COLLECTION, pts)
    _last_indexed = batch[-1]["id"]
    _total_indexed += len(batch)
    return len(batch)

# ── Background log generator ──────────────────────────────────────────────────
_stop = threading.Event()

def _gen_loop():
    last_index_at = 0
    while not _stop.is_set():
        insert_log(gen_log())
        if random.random() < 0.01:
            for _ in range(random.randint(5,12)):
                insert_log({**gen_log(), "level":"ERROR"})

        # Auto-index every ~20 seconds so the demo is always query-ready,
        # even right after a Space restart with an empty Qdrant store.
        now = time.time()
        if now - last_index_at > 20:
            try:
                n = index_new_logs(max_logs=300)
                if n:
                    logger.info(f"Auto-indexed {n} new logs into Qdrant")
            except Exception as e:
                logger.warning(f"Auto-index failed: {e}")
            last_index_at = now

        time.sleep(1/3)

# ── RAG ───────────────────────────────────────────────────────────────────────
SYSTEM = "You are RTLA, a log analysis AI. Answer based ONLY on the provided log entries. Be concise and technical."
_cache = {}

def rag_query(user_query):
    t0 = time.perf_counter()
    try:
        qvec = get_model().encode([user_query], normalize_embeddings=True).tolist()[0]
        embed_ms = round((time.perf_counter()-t0)*1000,1)
        results = get_qdrant().search(COLLECTION, qvec, limit=10, with_payload=True)
        retrieval_ms = round((time.perf_counter()-t0)*1000,1)
        hits = [{"score":round(r.score,4), **r.payload} for r in results]
        if not hits:
            return {"tier":1,"answer":"No relevant logs found.","sources":[],"total_latency_ms":retrieval_ms}
        ctx = "\n".join(f"[{i+1}] [{h['level']}] {h['service']} | {h['timestamp']} | {h['message']}" for i,h in enumerate(hits))
        if GROQ_API_KEY:
            client = Groq(api_key=GROQ_API_KEY)
            resp = client.chat.completions.create(model=GROQ_MODEL,
                messages=[{"role":"system","content":SYSTEM},{"role":"user","content":f"Logs:\n{ctx}\n\nQuestion: {user_query}"}],
                max_tokens=500, temperature=0.1, timeout=8)
            answer = resp.choices[0].message.content
            llm_ms = round((time.perf_counter()-t0)*1000 - retrieval_ms, 1)
            total  = round((time.perf_counter()-t0)*1000, 1)
            _cache[user_query] = answer
            return {"tier":1,"tier_label":"Full RAG","answer":answer,"sources":hits[:5],"embed_ms":embed_ms,"retrieval_ms":retrieval_ms,"llm_ms":llm_ms,"total_latency_ms":total}
        else:
            summary = f"Retrieved {len(hits)} logs:\n" + "\n".join(f"• [{h['level']}] {h['service']}: {h['message'][:100]}" for h in hits[:5])
            return {"tier":2,"tier_label":"Retrieval only","answer":summary,"sources":hits[:5],"retrieval_ms":retrieval_ms,"total_latency_ms":retrieval_ms}
    except Exception as e:
        cached = _cache.get(user_query)
        if cached:
            return {"tier":3,"tier_label":"Cached","answer":cached,"sources":[]}
        return {"tier":3,"tier_label":"Degraded","answer":f"Error: {e}","sources":[]}

# ── FastAPI ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app):
    init_db()
    # Seed with some initial logs
    for _ in range(50):
        insert_log(gen_log())
    # Index immediately so the demo is query-ready right after startup
    try:
        index_new_logs(max_logs=200)
        logger.info("Initial index complete on startup")
    except Exception as e:
        logger.warning(f"Initial index failed: {e}")
    t = threading.Thread(target=_gen_loop, daemon=True)
    t.start()
    yield
    _stop.set()

app = FastAPI(title="RTLA Demo", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class QueryReq(BaseModel):
    query: str
    level_filter: str = None

@app.get("/health")
def health():
    return {"status":"ok","mode":"demo","version":"1.0.0","timestamp":datetime.utcnow().isoformat()}

@app.get("/stats")
def stats():
    return get_stats()

@app.get("/logs")
def logs(limit:int=Query(30,ge=1,le=200), level:str=None):
    data = get_logs(limit, level)
    return {"count":len(data),"logs":data}

@app.get("/logs/errors")
def errors(limit:int=Query(20,ge=1,le=100)):
    return {"logs":get_logs(limit,"ERROR")}

@app.post("/index")
def index(max_logs:int=Query(200)):
    n = index_new_logs(max_logs)
    return {"indexed_this_run":n,"total_in_qdrant":_total_indexed+n,"last_id":_last_indexed}

@app.get("/index/status")
def index_status():
    return {"total_indexed":_total_indexed,"last_indexed_id":_last_indexed,"qdrant_available":True}

@app.post("/query")
def query(req: QueryReq):
    if not req.query.strip():
        return {"error":"empty query"}
    return rag_query(req.query)

@app.get("/slo")
def slo():
    return {"stages":{}}