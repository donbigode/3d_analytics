"""Embedding helpers — focus on cosine_similarity (no model load)."""
from backend.core.trends.embeddings import cosine_similarity


def test_identical_vectors():
    v = [0.1, 0.2, 0.3]
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-9


def test_orthogonal_vectors():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_opposite_vectors():
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == -1.0


def test_zero_vector_defensive():
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_length_mismatch_defensive():
    assert cosine_similarity([1.0], [1.0, 0.0]) == 0.0
