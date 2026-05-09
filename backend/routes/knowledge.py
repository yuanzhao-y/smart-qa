"""Knowledge base stats and chunk listing endpoints."""

from fastapi import APIRouter

from backend.vector_store import _get_collection

router = APIRouter()


@router.get("/stats")
async def stats():
    """Get knowledge base statistics."""
    from backend.vector_store import get_stats
    return get_stats()


@router.get("/chunks")
async def list_chunks(page: int = 1, page_size: int = 20, source: str = None):
    """List all indexed chunks with content and metadata. Optional source filter."""
    collection = _get_collection()

    if source:
        results = collection.get(
            where={"source": source},
            include=["documents", "metadatas"],
        )
        all_ids = results["ids"]
        total = len(all_ids)
        if total == 0:
            return {"chunks": [], "total": 0, "page": 1, "pages": 0, "source": source}
        start = (page - 1) * page_size
        end = min(start + page_size, total)
        chunks = []
        for i in range(start, end):
            meta = results["metadatas"][i]
            chunks.append({
                "id": results["ids"][i],
                "content": results["documents"][i],
                "source": meta.get("source", "未知"),
                "page": meta.get("page") or meta.get("paragraph") or meta.get("chunk_index", ""),
                "chunk_index": meta.get("chunk_index", ""),
            })
        return {
            "chunks": chunks,
            "total": total,
            "page": page,
            "pages": (total + page_size - 1) // page_size,
            "source": source,
        }

    total = collection.count()
    if total == 0:
        return {"chunks": [], "total": 0, "page": 1, "pages": 0}

    offset = (page - 1) * page_size
    limit = min(page_size, total - offset)
    if limit <= 0:
        return {"chunks": [], "total": total, "page": page, "pages": (total + page_size - 1) // page_size}

    results = collection.get(
        offset=offset,
        limit=limit,
        include=["documents", "metadatas"],
    )
    chunks = []
    for i in range(len(results["ids"])):
        meta = results["metadatas"][i]
        chunks.append({
            "id": results["ids"][i],
            "content": results["documents"][i],
            "source": meta.get("source", "未知"),
            "page": meta.get("page") or meta.get("paragraph") or meta.get("chunk_index", ""),
            "chunk_index": meta.get("chunk_index", ""),
        })

    return {
        "chunks": chunks,
        "total": total,
        "page": page,
        "pages": (total + page_size - 1) // page_size,
    }
