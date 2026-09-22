"""
Session router — explicit session lifecycle for both pipelines.

Note: /translate/forward and /translate/quick-phrase already create their
own Pipeline A session internally (see translate.py), because that flow
is one-shot per request. This router is for:
  - Pipeline B, where a session spans a whole recognition interaction
    (opened when the signer starts, closed when they finish), and
  - fetching session history/detail for either pipeline.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException

from app.config import settings
from app.database.local_db import get_connection
from app.models.session import SessionCreate, SessionResponse, SessionEndRequest

router = APIRouter(prefix="/session", tags=["session"])


@router.get("/health")
async def session_health():
    return {"status": "ok", "service": "session"}


@router.post("", response_model=SessionResponse)
async def create_session(body: SessionCreate):
    conn = get_connection()
    try:
        started_at = datetime.now(timezone.utc).isoformat()
        kiosk_id = body.kiosk_id or settings.KIOSK_ID
        cursor = conn.execute(
            "INSERT INTO sessions (kiosk_id, started_at, direction) VALUES (?, ?, ?)",
            (kiosk_id, started_at, body.direction)
        )
        conn.commit()
        return SessionResponse(
            id=cursor.lastrowid, kiosk_id=kiosk_id,
            started_at=started_at, ended_at=None, direction=body.direction
        )
    finally:
        conn.close()


@router.post("/end")
async def end_session(body: SessionEndRequest):
    conn = get_connection()
    try:
        ended_at = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ?",
            (ended_at, body.session_id)
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Session {body.session_id} not found")
        return {"success": True, "ended_at": ended_at}
    finally:
        conn.close()


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: int):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, kiosk_id, started_at, ended_at, direction FROM sessions WHERE id = ?",
            (session_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        return SessionResponse(
            id=row[0], kiosk_id=row[1], started_at=row[2], ended_at=row[3], direction=row[4]
        )
    finally:
        conn.close()
