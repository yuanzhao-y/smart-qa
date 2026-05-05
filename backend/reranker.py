"""Reranker using CrossEncoder for reordering retrieval results."""

import heapq

from sentence_transformers import CrossEncoder

from backend.config import settings

_model = None


def _get_model() -> CrossEncoder:
    global _model
    if _model is None:
        _model = CrossEncoder(settings.reranker_model)
    return _model


def rerank(query: str, docs: list[dict], top_n: int = None) -> list[dict]:
    """Rerank documents using cross-encoder scoring.

    Args:
        query: The user query.
        docs: List of dicts with 'content' key.
        top_n: Number of top results to return. Defaults to config.

    Returns:
        Reranked list of docs, sorted by relevance score descending.
    """
    if not docs:
        return []

    if top_n is None:
        top_n = settings.rerank_top_n

    model = _get_model()

    pairs = [(query, doc["content"]) for doc in docs]
    scores = model.predict(pairs)

    for doc, score in zip(docs, scores):
        doc["rerank_score"] = float(score)

    # Use heapq for partial sort when top_n < len(docs)
    if top_n < len(docs):
        top_docs = heapq.nlargest(top_n, docs, key=lambda x: x["rerank_score"])
    else:
        top_docs = sorted(docs, key=lambda x: x["rerank_score"], reverse=True)

    return top_docs
