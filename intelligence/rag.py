"""
intelligence/rag.py  (Phase 3 — instrumented)
──────────────────────────────────────────────
llm stage SLO budget: 250 ms

Instruments:
  • rtla_stage_latency_seconds{stage="llm"}
  • rtla_slo_violations_total{stage="llm"}
  • rtla_llm_calls_total{tier="primary"|"fallback"|"cache"}
  • rtla_llm_errors_total{tier=...}
  • rtla_rag_queries_total
  • rtla_active_rag_requests (gauge)

Preserves the existing 3-tier graceful degradation:
  Tier 1 → Groq Llama-3.3-70B (primary)
  Tier 2 → shorter context fallback
  Tier 3 → keyword/heuristic answer (no LLM)
"""

import logging
import time
from typing import Optional

from monitoring import (
    llm_calls_total,
    llm_errors_total,
    rag_queries_total,
    active_rag_requests,
)
from monitoring.slo import measure_stage_async

log = logging.getLogger("rtla.rag")


class RAGPipeline:
    """
    Drop-in replacement for your existing RAGPipeline.
    Wire in your actual Groq client, vector_store, and embedder below.
    """

    def __init__(self, groq_client, vector_store, embedder):
        self.groq = groq_client
        self.vector_store = vector_store
        self.embedder = embedder

    async def query(self, question: str, top_k: int = 5) -> dict:
        """
        Full RAG query with SLO instrumentation across all 3 tiers.
        Returns:
            {
                "answer": str,
                "tier": int,
                "context_docs": int,
                "latency_ms": float,
            }
        """
        rag_queries_total.inc()
        active_rag_requests.inc()
        t0 = time.perf_counter()

        try:
            # Step 1: embed the question (measured by embedder.py)
            query_vec = await self.embedder.embed_async(question)
            if query_vec is None:
                return await self._tier3_fallback(question, t0)

            # Step 2: vector search
            docs = await self.vector_store.search(query_vec, top_k=top_k)
            context = "\n\n".join(d["text"] for d in docs[:top_k])

            # Step 3: LLM call — Tier 1
            answer = await self._call_llm_tier1(question, context)
            if answer is not None:
                return {
                    "answer": answer,
                    "tier": 1,
                    "context_docs": len(docs),
                    "latency_ms": (time.perf_counter() - t0) * 1000,
                }

            # Step 4: Tier 2 — shorter context
            answer = await self._call_llm_tier2(question, context)
            if answer is not None:
                return {
                    "answer": answer,
                    "tier": 2,
                    "context_docs": len(docs),
                    "latency_ms": (time.perf_counter() - t0) * 1000,
                }

            # Step 5: Tier 3 — keyword heuristic
            return await self._tier3_fallback(question, t0)

        finally:
            active_rag_requests.dec()

    # ── Tier 1: primary Groq call ──────────────────────────────────────────
    async def _call_llm_tier1(self, question: str, context: str) -> Optional[str]:
        llm_calls_total.labels(tier="primary").inc()
        try:
            async with measure_stage_async("llm"):
                resp = await self.groq.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are an expert log analyst. "
                                "Answer questions about log data concisely and precisely."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Context logs:\n{context}\n\nQuestion: {question}"
                            ),
                        },
                    ],
                    max_tokens=512,
                    temperature=0.1,
                )
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            llm_errors_total.labels(tier="primary").inc()
            log.warning("Tier-1 LLM failed: %s — falling back to Tier 2", exc)
            return None

    # ── Tier 2: shorter context / smaller prompt ───────────────────────────
    async def _call_llm_tier2(self, question: str, context: str) -> Optional[str]:
        llm_calls_total.labels(tier="fallback").inc()
        # Truncate context to first 500 chars
        short_ctx = context[:500] if len(context) > 500 else context
        try:
            async with measure_stage_async("llm"):
                resp = await self.groq.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                f"Logs (truncated):\n{short_ctx}\n\nQ: {question}"
                            ),
                        }
                    ],
                    max_tokens=256,
                    temperature=0.0,
                )
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            llm_errors_total.labels(tier="fallback").inc()
            log.warning("Tier-2 LLM failed: %s — using Tier 3", exc)
            return None

    # ── Tier 3: heuristic / no LLM ────────────────────────────────────────
    async def _tier3_fallback(self, question: str, t0: float) -> dict:
        llm_calls_total.labels(tier="cache").inc()
        log.info("Using Tier-3 keyword fallback for question: %s", question[:80])
        q_lower = question.lower()
        if "error" in q_lower or "fail" in q_lower:
            answer = "Unable to reach LLM. Based on recent logs, check ERROR-level entries for root cause."
        elif "warn" in q_lower:
            answer = "Unable to reach LLM. Review WARN-level log entries for potential issues."
        else:
            answer = "LLM temporarily unavailable. Please retry or check /logs endpoint directly."

        return {
            "answer": answer,
            "tier": 3,
            "context_docs": 0,
            "latency_ms": (time.perf_counter() - t0) * 1000,
        }