import logging
from sentence_transformers import SentenceTransformer

logger = logging.getLogger("rtla.embedder")

MODEL_NAME = "all-MiniLM-L6-v2"
VECTOR_DIM  = 384

_model = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {MODEL_NAME} …")
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("Embedding model ready.")
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    model = get_model()
    vectors = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    return vectors.tolist()


def embed_one(text: str) -> list[float]:
    return embed([text])[0]