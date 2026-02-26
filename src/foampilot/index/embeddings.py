"""Local embedding model for semantic search of tutorial cases.

Uses sentence-transformers/all-MiniLM-L6-v2 for local, offline embeddings.
No external API calls.
"""

from __future__ import annotations

import numpy as np
import structlog

log = structlog.get_logger(__name__)

_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_model = None


def _get_model():
    """Lazily load the embedding model (expensive on first call)."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            log.info("loading_embedding_model", model=_MODEL_NAME)
            _model = SentenceTransformer(_MODEL_NAME)
            log.info("embedding_model_loaded")
        except ImportError:
            log.warning(
                "sentence_transformers_not_installed",
                detail="Install with: pip install sentence-transformers",
            )
            return None
    return _model


def embed_text(text: str) -> list[float] | None:
    """Compute an embedding vector for a single text string.

    Args:
        text: Text to embed.

    Returns:
        List of floats (384-dimensional), or None if model unavailable.
    """
    model = _get_model()
    if model is None:
        return None
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()


def embed_batch(texts: list[str]) -> list[list[float]] | None:
    """Compute embeddings for a batch of texts.

    Args:
        texts: List of strings.

    Returns:
        List of embedding vectors, or None if model unavailable.
    """
    model = _get_model()
    if model is None:
        return None
    vecs = model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
    return vecs.tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two normalized embedding vectors."""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    dot = float(np.dot(va, vb))
    norm = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return dot / norm if norm > 0 else 0.0


def top_k_similar(
    query_embedding: list[float],
    embeddings: list[list[float]],
    k: int = 10,
) -> list[tuple[int, float]]:
    """Find the top-k most similar embeddings to a query.

    Args:
        query_embedding: Query vector.
        embeddings: List of candidate vectors.
        k: Number of results.

    Returns:
        List of (index, similarity_score) sorted by descending similarity.
    """
    if not embeddings:
        return []
    q = np.array(query_embedding, dtype=np.float32)
    matrix = np.array(embeddings, dtype=np.float32)
    scores = matrix @ q  # dot product (vectors are normalized)
    top_indices = np.argsort(scores)[::-1][:k]
    return [(int(i), float(scores[i])) for i in top_indices]
