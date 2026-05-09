"""Vector store operations using ChromaDB."""

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import chromadb
from sentence_transformers import SentenceTransformer

from backend.config import settings
from backend import bm25_search
from backend.reranker import rerank

# Global instances (lazy init)
_model = None
_collection = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        _collection = client.get_or_create_collection(
            name="docs_v2",
            metadata={"hnsw:space": "cosine"}
        )
    return _collection


def add_documents(chunks: list[dict]) -> int:
    """Add document chunks to the vector store.

    Returns the number of chunks added.
    """
    if not chunks:
        return 0

    model = _get_model()
    collection = _get_collection()

    texts = [c["content"] for c in chunks]
    embeddings = model.encode(texts, show_progress_bar=False).tolist()

    ids = [str(uuid.uuid4()) for _ in chunks]

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=[c["metadata"] for c in chunks]
    )

    # Also add to BM25 index
    bm25_search.add_chunks(chunks)

    return len(chunks)


def vector_search(query: str, top_k: int = None) -> list[dict]:
    """Search for similar documents using vector similarity."""
    if top_k is None:
        top_k = settings.top_k

    model = _get_model()
    collection = _get_collection()

    if collection.count() == 0:
        return []

    query_embedding = model.encode([query], show_progress_bar=False).tolist()

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=min(top_k, collection.count())
    )

    docs = []
    for i in range(len(results["ids"][0])):
        docs.append({
            "content": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "score": 1 - results["distances"][0][i]
        })

    return docs


def _rrf_fuse(vector_docs: list[dict], bm25_docs: list[dict], k: int = 60) -> list[dict]:
    """Merge two ranked lists using Reciprocal Rank Fusion.

    RRF score = sum(1 / (k + rank_i)) across lists.
    """
    scores = {}
    content_map = {}

    for rank, doc in enumerate(vector_docs):
        key = doc["content"]
        scores[key] = scores.get(key, 0) + 1.0 / (k + rank + 1)
        content_map[key] = doc

    for rank, doc in enumerate(bm25_docs):
        key = doc["content"]
        scores[key] = scores.get(key, 0) + 1.0 / (k + rank + 1)
        if key not in content_map:
            content_map[key] = doc

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    results = []
    for content, score in ranked:
        doc = content_map[content].copy()
        doc["score"] = score
        results.append(doc)

    return results


def hybrid_search(query: str, top_k: int = None) -> list[dict]:
    """Search using both vector similarity and BM25 keyword matching.

    Results are merged using Reciprocal Rank Fusion (RRF),
    then optionally reranked with a cross-encoder model.
    Vector and BM25 searches run in parallel for lower latency.
    """
    if top_k is None:
        top_k = settings.top_k

    # Get more candidates from each retriever for better fusion
    fetch_k = top_k * 2

    # Run both searches in parallel
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_vector = executor.submit(vector_search, query, fetch_k)
        future_bm25 = executor.submit(bm25_search.search, query, fetch_k)
        vector_docs = future_vector.result()
        bm25_docs = future_bm25.result()

    # Fuse results
    fused = _rrf_fuse(vector_docs, bm25_docs)

    # Rerank with cross-encoder if enabled
    if settings.enable_rerank:
        return rerank(query, fused, top_n=top_k)

    return fused[:top_k]


def rebuild_bm25_from_store():
    """Load all documents from ChromaDB and rebuild BM25 index.

    Called on startup so hybrid search works after restart.
    """
    collection = _get_collection()
    if collection.count() == 0:
        return

    # Fetch all documents from ChromaDB
    results = collection.get(include=["documents", "metadatas"])
    chunks = []
    for i in range(len(results["ids"])):
        chunks.append({
            "content": results["documents"][i],
            "metadata": results["metadatas"][i]
        })

    bm25_search.rebuild_index(chunks)


def get_stats() -> dict:
    collection = _get_collection()
    return {"total_chunks": collection.count()}


def delete_by_source(source: str):
    """Delete all chunks whose metadata source matches the given filename."""
    collection = _get_collection()
    collection.delete(where={"source": source})
    # Also remove from BM25 index
    bm25_search.delete_by_source(source)
