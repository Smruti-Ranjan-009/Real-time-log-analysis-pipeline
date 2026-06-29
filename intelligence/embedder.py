"""
intelligence/embedder.py  (Phase 3 — instrumented)
───────────────────────────────────────────────────
embed stage SLO budget: 60 ms
"""

import logging
from typing import List, Optional

from monitoring import embed_errors_total
from monitoring.slo import async_timed_stage, measure_stage

log = logging.getLogger("rtla.embedder")


class LogEmbedder:
    """
    Wraps a sentence-transformer model (or any embedding backend).
    Replace `_load_model` with your actual model loader.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            log.info("Loading embedding model: %s", self.model_name)
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                log.info("Embedding model loaded.")
            except ImportError:
                log.error("sentence-transformers not installed.")
                raise

    # ── sync path ──────────────────────────────────────────────────────────
    def embed(self, text: str) -> Optional[List[float]]:
        """
        Embed a single string.
        Measures rtla_stage_latency_seconds{stage="embed"}.
        """
        self._ensure_model()
        with measure_stage("embed"):
            try:
                vec = self._model.encode(text, normalize_embeddings=True)
                return vec.tolist()
            except Exception as exc:
                embed_errors_total.inc()
                log.error("Embedding failed: %s", exc)
                return None

    def embed_batch(self, texts: List[str]) -> Optional[List[List[float]]]:
        """
        Embed a batch of strings under a single 'embed' stage measurement.
        """
        self._ensure_model()
        with measure_stage("embed"):
            try:
                vecs = self._model.encode(texts, normalize_embeddings=True, batch_size=32)
                return [v.tolist() for v in vecs]
            except Exception as exc:
                embed_errors_total.inc()
                log.error("Batch embedding failed: %s", exc)
                return None

    # ── async path (for use inside FastAPI async endpoints) ────────────────
    async def embed_async(self, text: str) -> Optional[List[float]]:
        """
        Async wrapper: runs the CPU-bound model in a thread pool.
        Measures the total wall-clock time including the thread hand-off.
        """
        import asyncio
        self._ensure_model()
        async with _AsyncEmbedContext(self, text) as result:
            return result


class _AsyncEmbedContext:
    """Helper to run sync embed inside measure_stage_async."""

    def __init__(self, embedder: LogEmbedder, text: str):
        self._embedder = embedder
        self._text = text
        self._result = None

    async def __aenter__(self):
        import asyncio
        loop = asyncio.get_event_loop()
        from monitoring.slo import measure_stage_async
        async with measure_stage_async("embed"):
            try:
                self._result = await loop.run_in_executor(
                    None,
                    lambda: self._embedder._model.encode(
                        self._text, normalize_embeddings=True
                    ).tolist(),
                )
            except Exception as exc:
                embed_errors_total.inc()
                log.error("Async embedding failed: %s", exc)
                self._result = None
        return self._result

    async def __aexit__(self, *_):
        pass