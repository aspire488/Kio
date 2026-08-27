"""
companion/semantic.py — Semantic Similarity Engine.

Replaces token-overlap matching with real semantic similarity using
sentence-transformers. Free, local, no API required.

Uses a lightweight model (all-MiniLM-L6-v2: ~80MB, fast on CPU)
for belief matching, observation matching, and situation relevance.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Lazy-loaded model (avoids startup cost when companion isn't used)
_model = None
_model_name = "all-MiniLM-L6-v2"


def _get_model():
    """Lazy-load the sentence-transformer model."""
    global _model
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(_model_name)
        logger.info("[SEMANTIC] Loaded model: %s", _model_name)
        return _model
    except Exception as exc:
        logger.warning("[SEMANTIC] Failed to load sentence-transformers: %s", exc)
        return None


def compute_embedding(text: str) -> Optional[np.ndarray]:
    """Compute a single embedding vector for text."""
    model = _get_model()
    if model is None:
        return None
    try:
        return model.encode(text, normalize_embeddings=True)
    except Exception:
        return None


def compute_embeddings(texts: List[str]) -> Optional[np.ndarray]:
    """Compute embeddings for a batch of texts. Returns (N, dim) array."""
    model = _get_model()
    if model is None or not texts:
        return None
    try:
        return model.encode(texts, normalize_embeddings=True, batch_size=32)
    except Exception:
        return None


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    if a is None or b is None:
        return 0.0
    return float(np.dot(a, b))


def find_semantically_similar(
    query: str,
    candidates: List[Tuple[str, float]],  # (text, base_score)
    threshold: float = 0.25,
    top_k: int = 10,
) -> List[Tuple[int, float]]:
    """Find semantically similar candidates to a query.
    
    Args:
        query: The text to match against
        candidates: List of (text, base_score) tuples
        threshold: Minimum semantic similarity to consider
        top_k: Maximum results to return
    
    Returns:
        List of (index, combined_score) sorted by score descending.
        Combined score = semantic_sim * 0.7 + base_score * 0.3
    """
    if not candidates:
        return []
    
    model = _get_model()
    if model is None:
        # Fallback to pure base_score ranking
        scored = [(i, s) for i, (_, s) in enumerate(candidates)]
        scored.sort(key=lambda x: -x[1])
        return [(i, s) for i, s in scored[:top_k] if s > threshold]
    
    try:
        query_emb = model.encode(query, normalize_embeddings=True)
        cand_texts = [c[0] for c in candidates]
        cand_embs = model.encode(cand_texts, normalize_embeddings=True, batch_size=32)
        
        # Compute cosine similarities
        sims = np.dot(cand_embs, query_emb)  # (N,)
        
        # Combine with base scores
        results = []
        for i, (sim, (_, base)) in enumerate(zip(sims, candidates)):
            if sim >= threshold or base >= threshold:
                combined = float(sim) * 0.7 + base * 0.3
                results.append((i, combined))
        
        results.sort(key=lambda x: -x[1])
        return results[:top_k]
    except Exception as exc:
        logger.debug("[SEMANTIC] Batch encoding failed: %s", exc)
        # Fallback
        scored = [(i, s) for i, (_, s) in enumerate(candidates)]
        scored.sort(key=lambda x: -x[1])
        return [(i, s) for i, s in scored[:top_k] if s > threshold]


def semantic_match_score(text_a: str, text_b: str) -> float:
    """Compute semantic similarity between two texts. Returns 0.0-1.0."""
    model = _get_model()
    if model is None:
        # Token overlap fallback
        tokens_a = set(text_a.lower().split())
        tokens_b = set(text_b.lower().split())
        if not tokens_a or not tokens_b:
            return 0.0
        return len(tokens_a & tokens_b) / max(len(tokens_a | tokens_b), 1)
    
    try:
        embs = model.encode([text_a, text_b], normalize_embeddings=True)
        return float(np.dot(embs[0], embs[1]))
    except Exception:
        return 0.0


def is_available() -> bool:
    """Check if the semantic engine is available."""
    return _get_model() is not None
