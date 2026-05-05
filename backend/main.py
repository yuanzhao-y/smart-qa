"""FastAPI main application."""

import asyncio
import json
import os
import re
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.config import settings
from backend.document_loader import load_document
from backend.text_splitter import split_texts
from backend.semantic_splitter import semantic_split
from backend.vector_store import add_documents, hybrid_search, get_stats, rebuild_bm25_from_store, delete_by_source
from backend.query_rewriter import hyde_rewrite
from backend.llm import chat, chat_stream
from backend.summarizer import generate_summary
from backend.evaluator import evaluate_answer
from backend.compressor import compress_history
from backend.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Preload models and rebuild index on startup."""
    logger.info("=== Smart QA 启动 ===")
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


app = FastAPI(title="Smart QA", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR = Path("data/sessions")
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
SUMMARIES_DIR = Path("data/summaries")
SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)


# Simple queries that don't need HyDE rewriting
_SIMPLE_PATTERN = re.compile(
    r'^(你好|hello|hi|hey|嗨|哈喽|thanks|thank|谢谢|ok|好的|嗯|'
    r'你是谁|你叫什么|你是干什么的|what are you|who are you|'
    r'帮[我助]|请问|可以.*吗|能.*吗|怎么.*|什么是.*|'
    r'\d{4}[-/]\d{1,2}|今天|现在|几点)',
    re.IGNORECASE
)


def _need_hyde(question: str) -> bool:
    """Decide if HyDE rewriting is needed. Skip for simple/short queries."""
    q = question.strip()
    if len(q) <= 15:
        return False
    if _SIMPLE_PATTERN.match(q):
        return False
    return True


class ChatRequest(BaseModel):
    question: str
    history: list[dict] | None = None
    stream: bool = False


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload and index a document (PDF, DOCX, TXT, MD)."""
    ext = Path(file.filename).suffix.lower()
    if ext not in (".pdf", ".docx", ".doc", ".txt", ".md"):
        raise HTTPException(400, f"Unsupported file type: {ext}")

    logger.info(f"[上传] 开始处理: {file.filename}")

    # Deduplication: remove old file with the same original name
    for old in UPLOAD_DIR.glob(f"*_{file.filename}"):
        old_id = old.name.split("_")[0]
        old_name = old.name.split("_", 1)[1] if "_" in old.name else old.name
        delete_by_source(old_name)
        old.unlink()
        # Remove old summary
        old_summary = SUMMARIES_DIR / f"{old_id}.json"
        if old_summary.exists():
            old_summary.unlink()
        logger.info(f"[上传] 去重删除旧文件: {old_name}")

    # Save file
    file_id = str(uuid.uuid4())[:8]
    save_path = UPLOAD_DIR / f"{file_id}_{file.filename}"
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        pages = load_document(str(save_path))
        # Normalize source to just the filename (not full path)
        for p in pages:
            p["metadata"]["source"] = file.filename
        logger.info(f"[上传] 文档解析完成: {len(pages)} 页")
        if settings.chunk_strategy == "semantic":
            chunks = semantic_split(pages)
            logger.info(f"[上传] 语义切片完成: {len(chunks)} 片段")
        else:
            chunks = split_texts(pages)
            logger.info(f"[上传] 固定切片完成: {len(chunks)} 片段")
        count = add_documents(chunks)
        logger.info(f"[上传] 索引完成: {count} 片段入库")

        # Generate document summary
        summary = await asyncio.to_thread(generate_summary, chunks)
        summary_path = SUMMARIES_DIR / f"{file_id}.json"
        summary_data = {
            "file_id": file_id,
            "filename": file.filename,
            "pages": len(pages),
            "chunks": count,
            **summary,
        }
        summary_path.write_text(json.dumps(summary_data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"[上传] 摘要生成完成: {summary.get('doc_type', '未知')}类型")
    except ValueError as e:
        logger.error(f"[上传] 处理失败: {e}")
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"[上传] 异常: {e}", exc_info=True)
        raise HTTPException(500, f"文档处理失败: {str(e)}")

    return {
        "filename": file.filename,
        "pages": len(pages),
        "chunks": count,
        "status": "indexed",
        "summary": summary,
    }


@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    """Ask a question. Returns answer with sources."""
    logger.info(f"[聊天] 问题: {req.question[:100]}")
    t0 = time.time()

    # Step 1: HyDE rewriting (skip for simple queries to reduce latency)
    if _need_hyde(req.question):
        hyde_query = await asyncio.to_thread(hyde_rewrite, req.question)
        logger.info(f"[聊天] HyDE 改写完成 ({time.time()-t0:.2f}s)")
    else:
        hyde_query = req.question
        logger.info(f"[聊天] 跳过 HyDE (简单问题)")

    # Step 2: Hybrid search (vector + BM25) — run in thread pool
    docs = await asyncio.to_thread(hybrid_search, hyde_query)
    logger.info(f"[聊天] 检索完成: {len(docs)} 片段 ({time.time()-t0:.2f}s)")

    if not docs:
        logger.warning("[聊天] 知识库为空")
        return {"answer": "知识库为空，请先上传文档。", "sources": []}

    # Compress history if too long
    history = req.history
    if history and len(history) > 10:
        history = await asyncio.to_thread(compress_history, history)
        logger.info(f"[聊天] 对话压缩完成: {len(req.history)} → {len(history)} 条")

    if req.stream:
        return StreamingResponse(
            chat_stream(req.question, docs, history),
            media_type="text/plain"
        )

    answer = await asyncio.to_thread(chat, req.question, docs, history)
    sources = list({
        doc["metadata"].get("source", "unknown")
        for doc in docs
    })
    logger.info(f"[聊天] 回答完成 ({time.time()-t0:.2f}s), 来源: {sources}")

    # Build citation references with chunk details
    citations = []
    seen = set()
    for doc in docs:
        src = doc["metadata"].get("source", "unknown")
        if src not in seen:
            seen.add(src)
            page = doc["metadata"].get("page") or doc["metadata"].get("paragraph") or doc["metadata"].get("chunk_index", "")
            citations.append({"source": src, "page": page})

    return {
        "answer": answer,
        "sources": sources,
        "citations": citations,
        "retrieved_chunks": len(docs)
    }


class EvaluateRequest(BaseModel):
    question: str
    answer: str
    docs: list[dict] | None = None


@app.post("/evaluate")
async def evaluate_endpoint(req: EvaluateRequest):
    """Evaluate answer quality using LLM-as-Judge."""
    docs = req.docs
    if not docs:
        # If docs not provided, do a search to get context
        docs = await asyncio.to_thread(hybrid_search, req.question)
    result = await asyncio.to_thread(evaluate_answer, req.question, req.answer, docs)
    return result


class FeedbackRequest(BaseModel):
    session_id: str
    message_index: int
    rating: int  # 1 = thumbs up, -1 = thumbs down
    comment: str | None = None


@app.post("/feedback")
async def submit_feedback(req: FeedbackRequest):
    """Submit user feedback for an answer."""
    path = SESSIONS_DIR / f"{req.session_id}.json"
    if not path.exists():
        raise HTTPException(404, "会话不存在")

    session = json.loads(path.read_text(encoding="utf-8"))
    messages = session.get("messages", [])

    if 0 <= req.message_index < len(messages):
        msg = messages[req.message_index]
        msg["feedback"] = {
            "rating": req.rating,
            "comment": req.comment,
            "timestamp": time.time(),
        }
        session["messages"] = messages
        session["updated_at"] = time.time()
        path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"status": "ok"}


@app.get("/stats")
async def stats():
    """Get knowledge base statistics."""
    return get_stats()


@app.get("/chunks")
async def list_chunks(page: int = 1, page_size: int = 20, source: str = None):
    """List all indexed chunks with content and metadata. Optional source filter."""
    from backend.vector_store import _get_collection
    collection = _get_collection()

    if source:
        # Filter by source metadata
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


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/documents")
async def list_documents():
    """List all uploaded documents."""
    docs = []
    for f in UPLOAD_DIR.iterdir():
        if f.is_file():
            stat = f.stat()
            # filename format: {file_id}_{original_name}
            parts = f.name.split("_", 1)
            file_id = parts[0]
            original_name = parts[1] if len(parts) > 1 else f.name
            docs.append({
                "file_id": file_id,
                "filename": original_name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })
    docs.sort(key=lambda x: x["modified"], reverse=True)
    # Attach summary if available
    for doc in docs:
        summary_path = SUMMARIES_DIR / f"{doc['file_id']}.json"
        if summary_path.exists():
            try:
                s = json.loads(summary_path.read_text(encoding="utf-8"))
                doc["summary"] = s.get("summary", "")
                doc["keywords"] = s.get("keywords", [])
                doc["doc_type"] = s.get("doc_type", "")
            except Exception:
                pass
    return {"documents": docs}


@app.delete("/documents/{file_id}")
async def delete_document(file_id: str):
    """Delete a document and its indexed chunks."""
    matched = list(UPLOAD_DIR.glob(f"{file_id}_*"))
    if not matched:
        raise HTTPException(404, "文档不存在")

    file_path = matched[0]
    original_name = file_path.name.split("_", 1)[1] if "_" in file_path.name else file_path.name

    delete_by_source(original_name)
    file_path.unlink()
    # Also delete summary
    summary_path = SUMMARIES_DIR / f"{file_id}.json"
    if summary_path.exists():
        summary_path.unlink()
    logger.info(f"[删除] 已删除文档: {original_name}")

    return {"status": "deleted", "filename": original_name}


@app.get("/documents/{file_id}/summary")
async def get_document_summary(file_id: str):
    """Get document summary."""
    summary_path = SUMMARIES_DIR / f"{file_id}.json"
    if not summary_path.exists():
        raise HTTPException(404, "摘要不存在")
    return json.loads(summary_path.read_text(encoding="utf-8"))


# ===== Chat Session Management =====

class SessionCreate(BaseModel):
    title: str = "新对话"

class SessionUpdate(BaseModel):
    messages: list[dict]
    title: str | None = None


@app.post("/sessions")
async def create_session(req: SessionCreate):
    """Create a new chat session."""
    session_id = str(uuid.uuid4())[:8]
    now = time.time()
    session = {
        "id": session_id,
        "title": req.title,
        "messages": [],
        "created_at": now,
        "updated_at": now,
    }
    path = SESSIONS_DIR / f"{session_id}.json"
    path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    return session


@app.get("/sessions")
async def list_sessions():
    """List all chat sessions, newest first."""
    sessions = []
    for f in SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            sessions.append({
                "id": data["id"],
                "title": data["title"],
                "created_at": data["created_at"],
                "updated_at": data["updated_at"],
                "message_count": len(data.get("messages", [])),
            })
        except Exception:
            continue
    sessions.sort(key=lambda x: x["updated_at"], reverse=True)
    return {"sessions": sessions}


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get a session with all messages."""
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(404, "会话不存在")
    return json.loads(path.read_text(encoding="utf-8"))


@app.put("/sessions/{session_id}")
async def update_session(session_id: str, req: SessionUpdate):
    """Update session messages."""
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(404, "会话不存在")
    session = json.loads(path.read_text(encoding="utf-8"))
    session["messages"] = req.messages
    if req.title is not None:
        session["title"] = req.title
    session["updated_at"] = time.time()
    path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    return session


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a chat session."""
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(404, "会话不存在")
    path.unlink()
    return {"status": "deleted"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
