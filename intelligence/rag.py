"""
RTLA Phase 2 — RAG Engine (Phase 3 instrumented)
Natural language queries over indexed logs.

3-tier graceful degradation:
  Tier 1 — Full RAG:        Qdrant retrieval + Groq LLM answer
  Tier 2 — Retrieval only:  Groq timed out / unavailable
  Tier 3 — Cached / minimal: Qdrant also unavailable
"""

import logging
import os
import time
from dotenv import load_dotenv
from groq import Groq

from .embedder import embed_one
from .vector_store import search, count

from monitoring import (
    llm_calls_total,
    llm_errors_total,
    rag_queries_total,
    active_rag_requests,
)
from monitoring.slo import measure_stage

load_dotenv()
logger = logging.getLogger("rtla.rag")

GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_TIMEOUT  = 8.0
TOP_K         = 10

_cache: dict[str, dict] = {}

SYSTEM_PROMPT = """\
You are RTLA, an expert real-time log analysis assistant for microservice systems.
You are given a set of relevant log entries retrieved from a live pipeline and must answer the user's question.

Rules:
- Base your answer ONLY on the provided log entries.
- Be concise, technical, and specific.
- Mention service names, error types, and timestamps when relevant.
- If you can identify a root cause or pattern, state it clearly.
- If the logs are insufficient to answer, say so honestly.
- Format counts and lists clearly when summarising multiple issues.
"""


# ── Public API ────────────────────────────────────────────────────────────────

def query_logs(user_query: str, level_filter: str = None) -> dict:
    """
    Main RAG entry point.
    Returns a dict with: tier, tier_label, answer, sources, latency info.
    """
    rag_queries_total.inc()
    active_rag_requests.inc()
    t0 = time.perf_counter()

    try:
        # ── Tier 3 guard: Qdrant availability ────────────────────────────────
        try:
            total_indexed = count()
            if total_indexed == 0:
                return _tier3(user_query, reason="No logs indexed yet — call POST /index first")
        except Exception as e:
            logger.warning(f"Qdrant unavailable: {e}")
            return _tier3(user_query, reason=f"Vector store unavailable: {e}")

        # ── Embed query ───────────────────────────────────────────────────────
        try:
            query_vector = embed_one(user_query)
            embed_ms = round((time.perf_counter() - t0) * 1000, 1)
        except Exception as e:
            return _tier3(user_query, reason=f"Embedding failed: {e}")

        # ── Retrieve from Qdrant ──────────────────────────────────────────────
        try:
            results = search(query_vector, top_k=TOP_K, level_filter=level_filter)
            retrieval_ms = round((time.perf_counter() - t0) * 1000, 1)
            logger.info(f"Retrieved {len(results)} logs in {retrieval_ms} ms")
        except Exception as e:
            logger.warning(f"Qdrant search failed: {e}")
            return _tier3(user_query, reason=f"Retrieval failed: {e}")

        if not results:
            return {
                "tier": 1,
                "tier_label": "Full RAG — no matching logs",
                "answer": "No relevant log entries found for your query. Try a different question or index more logs.",
                "sources": [],
                "embed_ms":     embed_ms,
                "retrieval_ms": retrieval_ms,
                "total_latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            }

        context = _build_context(results)

        # ── Tier 1: Groq LLM ─────────────────────────────────────────────────
        try:
            if not GROQ_API_KEY:
                raise ValueError("GROQ_API_KEY not configured in .env")

            llm_calls_total.labels(tier="primary").inc()
            answer, llm_ms = _call_groq(user_query, context)
            total_ms = round((time.perf_counter() - t0) * 1000, 1)

            response = {
                "tier":             1,
                "tier_label":       "Full RAG (Qdrant + Groq Llama 3)",
                "answer":           answer,
                "sources":          results[:5],
                "embed_ms":         embed_ms,
                "retrieval_ms":     retrieval_ms,
                "llm_ms":           llm_ms,
                "total_latency_ms": total_ms,
                "logs_searched":    total_indexed,
            }
            _cache[user_query] = {"answer": answer, "sources": results[:5]}
            return response

        except Exception as e:
            llm_errors_total.labels(tier="primary").inc()
            logger.warning(f"Groq failed ({e}) — degrading to Tier 2")
            return _tier2(user_query, results, embed_ms, retrieval_ms, t0, reason=str(e))

    finally:
        active_rag_requests.dec()


# ── Groq call ─────────────────────────────────────────────────────────────────

def _call_groq(user_query: str, context: str) -> tuple[str, float]:
    client = Groq(api_key=GROQ_API_KEY)
    t = time.perf_counter()
    with measure_stage("llm"):
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Relevant log entries:\n{context}\n\n"
                        f"Question: {user_query}"
                    ),
                },
            ],
            max_tokens=600,
            temperature=0.1,
            timeout=GROQ_TIMEOUT,
        )
    llm_ms = round((time.perf_counter() - t) * 1000, 1)
    logger.info(f"Groq response: {llm_ms} ms")
    return response.choices[0].message.content, llm_ms


# ── Context builder ───────────────────────────────────────────────────────────

def _build_context(results: list[dict]) -> str:
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(
            f"[{i}] [{r.get('level','?')}] {r.get('service','?')} "
            f"@ {r.get('timestamp','?')} | {r.get('message','?')} "
            f"(score: {r.get('score', 0):.3f})"
        )
    return "\n".join(lines)


# ── Degradation tiers ─────────────────────────────────────────────────────────

def _tier2(query, results, embed_ms, retrieval_ms, t0, reason):
    llm_calls_total.labels(tier="fallback").inc()
    return {
        "tier":                2,
        "tier_label":          "Retrieval only — Groq unavailable",
        "degradation_reason":  reason,
        "answer":              _summarise(results),
        "sources":             results[:5],
        "embed_ms":            embed_ms,
        "retrieval_ms":        retrieval_ms,
        "total_latency_ms":    round((time.perf_counter() - t0) * 1000, 1),
    }


def _tier3(query: str, reason: str) -> dict:
    llm_calls_total.labels(tier="cache").inc()
    cached = _cache.get(query)
    if cached:
        return {
            "tier":               3,
            "tier_label":         "Cached response — vector store unavailable",
            "degradation_reason": reason,
            "answer":             cached["answer"],
            "sources":            cached.get("sources", [])[:3],
            "note":               "Serving a cached response from a previous identical query.",
        }
    return {
        "tier":               3,
        "tier_label":         "Minimal response — all intelligence layers unavailable",
        "degradation_reason": reason,
        "answer":             (
            "RTLA intelligence layer is currently unavailable. "
            "Please check that Qdrant is running (docker-compose ps) "
            "and that GROQ_API_KEY is set in .env."
        ),
        "sources": [],
    }


def _summarise(results: list[dict]) -> str:
    if not results:
        return "No relevant logs found."
    by_level: dict[str, list] = {}
    for r in results:
        by_level.setdefault(r.get("level", "UNKNOWN"), []).append(r)
    lines = [f"Retrieved {len(results)} relevant log entries:\n"]
    for level, entries in sorted(by_level.items()):
        lines.append(f"{level} ({len(entries)}):")
        for e in entries[:3]:
            lines.append(f"  • [{e.get('service')}] {e.get('message','')[:120]}")
    return "\n".join(lines)