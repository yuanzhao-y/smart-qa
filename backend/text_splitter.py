"""Split documents into chunks for embedding."""

import re
from backend.config import settings


def _split_by_separators(text: str, separators: list[str]) -> list[str]:
    """Recursively split text by a list of separators."""
    if not separators:
        return [text] if text.strip() else []

    sep = separators[0]
    rest = separators[1:]
    parts = text.split(sep)

    result = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # If this part is still too long, try the next separator
        if len(part) > settings.chunk_size and rest:
            result.extend(_split_by_separators(part, rest))
        else:
            result.append(part)
    return result


def _merge_small_chunks(texts: list[str], chunk_size: int) -> list[str]:
    """Merge consecutive small chunks to approach chunk_size."""
    if not texts:
        return []

    merged = []
    current = ""

    for text in texts:
        # If adding this text exceeds chunk_size, save current and start new
        if current and len(current) + len(text) + 1 > chunk_size:
            merged.append(current.strip())
            current = text
        else:
            current = current + "\n" + text if current else text

    if current.strip():
        merged.append(current.strip())

    return merged


def split_texts(pages: list[dict]) -> list[dict]:
    """Split page-level documents into coherent chunks.

    Strategy (no overlap to avoid confusing repetition):
    1. Split by paragraphs (double newline)
    2. Merge consecutive small paragraphs up to chunk_size
    3. If a single paragraph is too long, split by sentences
    4. If a single sentence is still too long, split by punctuation (。！？；)
    """
    chunk_size = settings.chunk_size

    # Ordered separators: paragraph -> sentence -> clause
    separators = [
        "\n\n",      # paragraphs
        "\n",        # single newlines
        "。",        # Chinese period
        "！",        # Chinese exclamation
        "？",        # Chinese question mark
        "；",        # Chinese semicolon
        ". ",        # English period
        "! ",        # English exclamation
        "? ",        # English question mark
        "，",        # Chinese comma (last resort)
        ", ",        # English comma
    ]

    chunks = []
    for page in pages:
        text = page["content"].strip()
        metadata = page["metadata"]

        if not text:
            continue

        # Step 1: Split by separators recursively
        parts = _split_by_separators(text, separators)

        # Step 2: Merge small consecutive parts
        merged = _merge_small_chunks(parts, chunk_size)

        # Step 3: Handle any remaining oversized chunks by force-cutting
        final_parts = []
        for part in merged:
            if len(part) <= chunk_size:
                final_parts.append(part)
            else:
                # Force cut at chunk_size, try to find a nearby break point
                while len(part) > chunk_size:
                    cut = chunk_size
                    # Look for a break point near the cut position
                    for sep in ["。", "！", "？", "；", ".", "!", "?", "；", "，", ","]:
                        pos = part.rfind(sep, chunk_size // 2, chunk_size)
                        if pos != -1:
                            cut = pos + len(sep)
                            break
                    final_parts.append(part[:cut].strip())
                    part = part[cut:].strip()
                if part:
                    final_parts.append(part)

        # Step 4: Build chunk objects
        for idx, chunk_text in enumerate(final_parts):
            if chunk_text:
                chunks.append({
                    "content": chunk_text,
                    "metadata": {**metadata, "chunk_index": idx}
                })

    return chunks
