"""BM25 keyword search for document chunks."""

import re

import jieba
from rank_bm25 import BM25Okapi

# Global state
_corpus: list[dict] = []  # [{content, metadata}, ...]
_tokenized_corpus: list[list[str]] = []
_bm25: BM25Okapi | None = None


def _tokenize(text: str) -> list[str]:
    """Tokenize using jieba for Chinese, simple split for English."""
    tokens = []
    for word in jieba.cut(text):
        word = word.strip()
        if not word:
            continue
        if re.search(r'[一-鿿]', word):
            tokens.append(word)
        elif word.isalnum():
            tokens.append(word.lower())
    return tokens


def rebuild_index(chunks: list[dict]):
    """Rebuild BM25 index from all chunks."""
    global _corpus, _tokenized_corpus, _bm25
    _corpus = chunks
    if chunks:
        _tokenized_corpus = [_tokenize(c["content"]) for c in chunks]
        _bm25 = BM25Okapi(_tokenized_corpus)
    else:
        _tokenized_corpus = []
        _bm25 = None


def add_chunks(chunks: list[dict]):
    """Add new chunks incrementally without full rebuild."""
    global _corpus, _tokenized_corpus, _bm25
    if not chunks:
        return
    new_tokenized = [_tokenize(c["content"]) for c in chunks]
    _corpus.extend(chunks)
    _tokenized_corpus.extend(new_tokenized)
    _bm25 = BM25Okapi(_tokenized_corpus)


def search(query: str, top_k: int = 5) -> list[dict]:
    """Search using BM25 keyword matching."""
    if _bm25 is None or not _corpus:
        return []

    tokens = _tokenize(query)
    scores = _bm25.get_scores(tokens)

    # Get top-k indices
    indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]

    results = []
    for idx, score in indexed:
        if score > 0:
            results.append({
                "content": _corpus[idx]["content"],
                "metadata": _corpus[idx]["metadata"],
                "bm25_score": float(score)
            })

    return results


def delete_by_source(source: str):
    """Remove chunks matching the source filename and rebuild index."""
    global _corpus
    _corpus = [c for c in _corpus if c["metadata"].get("source") != source]
    rebuild_index(_corpus)


def get_count() -> int:
    return len(_corpus)
