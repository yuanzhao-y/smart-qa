"""Chat, evaluation, and feedback endpoints."""

import re
import time
import json
import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.vector_store import hybrid_search
from backend.query_rewriter import hyde_rewrite
from backend.llm import chat, chat_stream
from backend.evaluator import evaluate_answer
from backend.compressor import compress_history
from backend.logger import logger

router = APIRouter()

SESSIONS_DIR = Path("data/sessions")
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

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


@router.post("/chat")
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
        logger.info(f"[聊天] 对话压缩完成: {len(req.history)} -> {len(history)} 条")

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


@router.post("/evaluate")
async def evaluate_endpoint(req: EvaluateRequest):
    """Evaluate answer quality using LLM-as-Judge."""
    docs = req.docs
    if not docs:
        docs = await asyncio.to_thread(hybrid_search, req.question)
    result = await asyncio.to_thread(evaluate_answer, req.question, req.answer, docs)
    return result


class FeedbackRequest(BaseModel):
    session_id: str
    message_index: int
    rating: int
    comment: str | None = None


@router.post("/feedback")
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
