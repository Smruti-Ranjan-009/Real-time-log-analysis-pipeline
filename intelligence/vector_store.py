"""
RTLA Phase 2 — Vector Store
Thin wrapper around Qdrant for log vector storage and retrieval.
Collection: rtla-logs  |  Vectors: 384-dim cosine
"""

import logging
import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

load_dotenv()
logger = logging.getLogger("rtla.vector_store")

QDRANT_HOST     = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT     = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION_NAME = "rtla-logs"
VECTOR_DIM      = 384

_client: QdrantClient = None


# ── Client ────────────────────────────────────────────────────────────────────

def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=5)
        logger.info(f"Qdrant client connected: {QDRANT_HOST}:{QDRANT_PORT}")
    return _client


# ── Collection ────────────────────────────────────────────────────────────────

def ensure_collection() -> None:
    client = get_client()
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        logger.info(f"Created Qdrant collection '{COLLECTION_NAME}'")
    else:
        logger.info(f"Qdrant collection '{COLLECTION_NAME}' already exists")


# ── Write ─────────────────────────────────────────────────────────────────────

def upsert_logs(points: list[dict]) -> None:
    """
    Upsert a batch of log vectors.
    Each point: { id: int, vector: list[float], payload: dict }
    """
    client = get_client()
    qdrant_points = [
        PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
        for p in points
    ]
    client.upsert(collection_name=COLLECTION_NAME, points=qdrant_points)


# ── Read ──────────────────────────────────────────────────────────────────────

def search(
    query_vector: list[float],
    top_k: int = 10,
    level_filter: str = None,
) -> list[dict]:
    """
    Semantic search over indexed logs.
    Optionally filter by log level (ERROR | WARN | INFO | DEBUG).
    Returns list of payloads + similarity scores.
    """
    client = get_client()

    query_filter = None
    if level_filter:
        query_filter = Filter(
            must=[FieldCondition(key="level", match=MatchValue(value=level_filter.upper()))]
        )

    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        limit=top_k,
        query_filter=query_filter,
        with_payload=True,
    )
    return [{"score": round(r.score, 4), **r.payload} for r in results]


def count() -> int:
    """Return total number of indexed log vectors."""
    return get_client().count(collection_name=COLLECTION_NAME).count
