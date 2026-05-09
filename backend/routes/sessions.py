"""Chat session management endpoints."""

import json
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

SESSIONS_DIR = Path("data/sessions")
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


class SessionCreate(BaseModel):
    title: str = "新对话"


class SessionUpdate(BaseModel):
    messages: list[dict]
    title: str | None = None


@router.post("/sessions")
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


@router.get("/sessions")
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


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get a session with all messages."""
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(404, "会话不存在")
    return json.loads(path.read_text(encoding="utf-8"))


@router.put("/sessions/{session_id}")
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


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a chat session."""
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(404, "会话不存在")
    path.unlink()
    return {"status": "deleted"}
