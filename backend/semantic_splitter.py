"""Semantic-aware text chunking using embedding similarity.

Instead of splitting by fixed separators, this module:
1. Splits text into paragraphs
2. Computes embeddings for each paragraph
3. Finds natural break points where semantic similarity drops
4. Merges paragraphs between break points up to chunk_size
"""

import logging
import re

import numpy as np

from backend.config import settings

logger = logging.getLogger("smartqa")

# Similarity threshold: paragraphs below this are considered topic boundaries
_SIMILARITY_THRESHOLD = 0.5


def _split_paragraphs(text: str) -> list[str]:
    """Split text into atomic paragraphs."""
    # Split by double newline first, then single newline for long blocks
    parts = re.split(r'\n{2,}', text)
    paragraphs = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # If still very long, split by single newline
        if len(part) > settings.chunk_size * 1.5:
            sub_parts = part.split('\n')
            paragraphs.extend(p.strip() for p in sub_parts if p.strip())
        else:
            paragraphs.append(part)
    return paragraphs


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _find_break_points(paragraphs: list[str], embeddings: np.ndarray) -> list[int]:
    """Find indices where topic changes based on semantic similarity.

    Returns list of break point indices (paragraphs after which to split).
    """
    if len(paragraphs) <= 1:
        return []

    break_points = [0]  # Always include the start

    for i in range(len(paragraphs) - 1):
        sim = _cosine_similarity(embeddings[i], embeddings[i + 1])

        # Also break if paragraph is very long
        is_long = len(paragraphs[i]) > settings.chunk_size * 0.8

        if sim < _SIMILARITY_THRESHOLD or is_long:
            break_points.append(i + 1)

    break_points.append(len(paragraphs))
    return break_points


def _merge_segments(paragraphs: list[str], break_points: list[int]) -> list[str]:
    """Merge paragraphs between break points, respecting chunk_size."""
    chunk_size = settings.chunk_size
    segments = []

    for i in range(len(break_points) - 1):
        start = break_points[i]
        end = break_points[i + 1]
        segment_paras = paragraphs[start:end]

        # Merge paragraphs in this segment
        merged = ""
        for para in segment_paras:
            if merged and len(merged) + len(para) + 1 > chunk_size:
                segments.append(merged.strip())
                merged = para
            else:
                merged = merged + "\n" + para if merged else para

        if merged.strip():
            # If the merged segment is still too long, force split
            if len(merged) > chunk_size:
                while len(merged) > chunk_size:
                    cut = chunk_size
                    for sep in ["。", "！", "？", ".", "!", "?", "；", "，", ","]:
                        pos = merged.rfind(sep, chunk_size // 2, chunk_size)
                        if pos != -1:
                            cut = pos + len(sep)
                            break
                    segments.append(merged[:cut].strip())
                    merged = merged[cut:].strip()
                if merged:
                    segments.append(merged)
            else:
                segments.append(merged)

    return segments


def semantic_split(pages: list[dict]) -> list[dict]:
    """Split documents using semantic similarity to find natural boundaries.

    Args:
        pages: List of page dicts with 'content' and 'metadata'.

    Returns:
        List of chunk dicts with 'content' and 'metadata'.
    """
    from backend.vector_store import _get_model
    model = _get_model()

    all_chunks = []

    for page in pages:
        text = page["content"].strip()
        metadata = page["metadata"]

        if not text:
            continue

        # Step 1: Split into paragraphs
        paragraphs = _split_paragraphs(text)
        if not paragraphs:
            continue

        if len(paragraphs) == 1:
            # Single paragraph, no need for semantic analysis
            if len(paragraphs[0]) <= settings.chunk_size:
                all_chunks.append({
                    "content": paragraphs[0],
                    "metadata": {**metadata, "chunk_index": 0}
                })
            else:
                # Force split long single paragraph
                chunks = _force_split(paragraphs[0])
                for idx, chunk in enumerate(chunks):
                    all_chunks.append({
                        "content": chunk,
                        "metadata": {**metadata, "chunk_index": idx}
                    })
            continue

        # Step 2: Compute embeddings
        embeddings = model.encode(paragraphs, show_progress_bar=False)

        # Step 3: Find break points
        break_points = _find_break_points(paragraphs, embeddings)

        # Step 4: Merge segments
        segments = _merge_segments(paragraphs, break_points)

        # Step 5: Build chunk objects
        for idx, segment in enumerate(segments):
            if segment:
                all_chunks.append({
                    "content": segment,
                    "metadata": {**metadata, "chunk_index": idx}
                })

    return all_chunks


def _force_split(text: str) -> list[str]:
    """Force split a long text at sentence boundaries."""
    chunk_size = settings.chunk_size
    chunks = []
    while len(text) > chunk_size:
        cut = chunk_size
        for sep in ["。", "！", "？", ".", "!", "?", "；", "，", ","]:
            pos = text.rfind(sep, chunk_size // 2, chunk_size)
            if pos != -1:
                cut = pos + len(sep)
                break
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        chunks.append(text)
    return chunks
