"""FastAPI main application — registers route modules."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.logger import logger

from backend.routes.documents import router as documents_router
from backend.routes.chat import router as chat_router
from backend.routes.sessions import router as sessions_router
from backend.routes.knowledge import router as knowledge_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Preload models and rebuild index on startup."""
    logger.info("=== Smart QA 启动 ===")
    from backend.vector_store import rebuild_bm25_from_store
    rebuild_bm25_from_store()
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _preload_models)
    yield
    logger.info("=== Smart QA 关闭 ===")


def _preload_models():
    """Preload embedding model, reranker, and ChromaDB collection."""
    from backend.vector_store import _get_model, _get_collection
    from backend.reranker import _get_model as _get_reranker
    from backend.llm import _get_client
    logger.info("预加载 embedding 模型...")
    _get_model()
    logger.info("预加载 ChromaDB...")
    _get_collection()
    if settings.enable_rerank:
        logger.info("预加载 reranker 模型...")
        _get_reranker()
    logger.info("预加载 LLM 客户端...")
    _get_client()
    logger.info("所有模型加载完成")


app = FastAPI(title="Smart QA", version="2.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register route modules
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(sessions_router)
app.include_router(knowledge_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
