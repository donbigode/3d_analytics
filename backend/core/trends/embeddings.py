"""Sentence embeddings for the trend radar's vector store.

Uses ``intfloat/multilingual-e5-small`` — 384-d, ~118 MB, runs on CPU in a
few ms per text. Good Portuguese coverage. Model is loaded lazily on first
call and cached at module level.

We DO NOT cache the model in the Docker image — it downloads on first run
into ~/.cache/huggingface inside the container. To avoid re-downloads in CI
or fresh dev environments, mount a volume at /root/.cache/huggingface if
needed.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Iterable

logger = logging.getLogger(__name__)

_MODEL_NAME = "intfloat/multilingual-e5-small"
_model = None


def _load() -> object:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("loading sentence-transformers model %s", _MODEL_NAME)
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def embed_sync(texts: Iterable[str]) -> list[list[float]]:
    """Synchronous embedding. Prefer :func:`embed` from async code."""
    items = [t if t.startswith("query:") or t.startswith("passage:") else f"passage: {t}" for t in texts]
    if not items:
        return []
    model = _load()
    arr = model.encode(items, normalize_embeddings=True, show_progress_bar=False)
    return [vec.tolist() for vec in arr]


async def embed(texts: Iterable[str]) -> list[list[float]]:
    """Async wrapper — runs the encoder in a thread to keep the event loop free."""
    return await asyncio.to_thread(embed_sync, list(texts))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity for two equal-length vectors.

    Since the model normalizes outputs, this is also the dot product, but the
    explicit form is kept for safety in case a caller passes a raw vector.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
