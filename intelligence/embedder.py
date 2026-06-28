"""
RTLA Phase 2 — Embedder
Lazy-loads sentence-transformers all-MiniLM-L6-v2 (90 MB, 384-dim).
Model is downloaded once on first call and cached in memory.
"""

import logging
from sentence_transformers import SentenceTransformer

logger = logging.getLogger("rtla.embedder")

MODEL_NAME = "all-MiniLM-L6-v2"
VECTOR_DIM  = 384

_model: SentenceTransformer = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {MODEL_NAME} …")
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("Embedding model ready.")
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings. Returns list of 384-dim float vectors."""
    model = get_model()
    vectors = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        normalize_embeddings=True,   # cosine similarity → dot product
    )
    return vectors.tolist()


def embed_one(text: str) -> list[float]:
    """Convenience wrapper for a single string."""
    return embed([text])[0]
