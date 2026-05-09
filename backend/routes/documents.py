"""Document upload, listing, deletion, and summary endpoints."""

import asyncio
import json
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException

from backend.config import settings
from backend.document_loader import load_document
from backend.text_splitter import split_texts
from backend.semantic_splitter import semantic_split
from backend.vector_store import add_documents, delete_by_source
from backend.summarizer import generate_summary
from backend.logger import logger

router = APIRouter()

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
SUMMARIES_DIR = Path("data/summaries")
SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload and index a document (PDF, DOCX, TXT, MD)."""
    ext = Path(file.filename).suffix.lower()
    if ext not in (".pdf", ".docx", ".doc", ".txt", ".md"):
        raise HTTPException(400, f"不支持的文件类型: {ext}")

    logger.info(f"[上传] 开始处理: {file.filename}")

    # Deduplication: remove old file with the same original name
    for old in UPLOAD_DIR.glob(f"*_{file.filename}"):
        old_id = old.name.split("_")[0]
        old_name = old.name.split("_", 1)[1] if "_" in old.name else old.name
        delete_by_source(old_name)
        old.unlink()
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


@router.get("/documents")
async def list_documents():
    """List all uploaded documents."""
    docs = []
    for f in UPLOAD_DIR.iterdir():
        if f.is_file():
            stat = f.stat()
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


@router.delete("/documents/{file_id}")
async def delete_document(file_id: str):
    """Delete a document and its indexed chunks."""
    matched = list(UPLOAD_DIR.glob(f"{file_id}_*"))
    if not matched:
        raise HTTPException(404, "文档不存在")

    file_path = matched[0]
    original_name = file_path.name.split("_", 1)[1] if "_" in file_path.name else file_path.name

    delete_by_source(original_name)
    file_path.unlink()

    summary_path = SUMMARIES_DIR / f"{file_id}.json"
    if summary_path.exists():
        summary_path.unlink()
    logger.info(f"[删除] 已删除文档: {original_name}")

    return {"status": "deleted", "filename": original_name}


@router.get("/documents/{file_id}/summary")
async def get_document_summary(file_id: str):
    """Get document summary."""
    summary_path = SUMMARIES_DIR / f"{file_id}.json"
    if not summary_path.exists():
        raise HTTPException(404, "摘要不存在")
    return json.loads(summary_path.read_text(encoding="utf-8"))
