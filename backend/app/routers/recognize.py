"""
app/routers/recognize.py

Pipeline B (Deaf -> hearing) entry point.

Only landmarks travel over this connection, never video/images — the
camera and MediaPipe extraction run in the browser (see architecture
notes), so this endpoint never sees raw frames, which matters for
privacy in a public workplace.

Wire format (JSON text frames over the WebSocket):
  client -> server:
    {"type": "landmarks", "frame": {"pose": [...], "left_hand": [...], "right_hand": [...]}}
    {"type": "pause"}   -- signer paused; force a recognition attempt on the current buffer
    {"type": "reset"}   -- clear the buffer (new sentence)
    {"type": "confirm", "recognition_id": <int>, "corrected_text": <str|null>}

  server -> client:
    {"type": "result", "status": "ok"|"buffering"|"recognizer_not_loaded",
     "gloss_sequence": [...], "sentence_text": "...", "recognition_id": <int|null>}
    {"type": "error", "detail": "..."}

Until a trained model is wired into app/services/recognition.py, every
"landmarks" frame will get back status="recognizer_not_loaded" — that's
expected, not a bug, and lets the frontend build/test the streaming and
confirmation flow ahead of the model being ready.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import settings
from ..database.local_db import (
    get_connection,
    insert_recognition_session,
    confirm_recognition_session,
)
from ..services.recognition import SignRecognizer

router = APIRouter(prefix="/recognize", tags=["recognize"])


def _open_session_b() -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO sessions (kiosk_id, started_at, direction) VALUES (?, ?, 'B')",
            (settings.KIOSK_ID, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


@router.websocket("/ws")
async def recognize_ws(websocket: WebSocket):
    await websocket.accept()
    recognizer = SignRecognizer()
    session_id = _open_session_b()

    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")

            if msg_type == "landmarks":
                frame = message.get("frame")
                if frame is None:
                    await websocket.send_json({"type": "error", "detail": "missing 'frame'"})
                    continue
                recognizer.add_frame(frame)
                result = await recognizer.recognize()

            elif msg_type == "pause":
                result = await recognizer.recognize()

            elif msg_type == "reset":
                recognizer.reset()
                continue

            elif msg_type == "confirm":
                recognition_id = message.get("recognition_id")
                corrected_text = message.get("corrected_text")
                if recognition_id is not None:
                    confirm_recognition_session(recognition_id, corrected_text)
                await websocket.send_json({"type": "confirmed", "recognition_id": recognition_id})
                continue

            else:
                await websocket.send_json({"type": "error", "detail": f"unknown type '{msg_type}'"})
                continue

            recognition_id = None
            if result.status == "ok" and result.gloss_sequence:
                recognition_id = insert_recognition_session(
                    session_id=session_id,
                    gloss_sequence=result.gloss_sequence,
                    sentence_text=result.sentence_text,
                    confidence=result.confidence,
                )

            await websocket.send_json({
                "type": "result",
                "status": result.status,
                "gloss_sequence": result.gloss_sequence,
                "sentence_text": result.sentence_text,
                "recognition_id": recognition_id,
            })

    except WebSocketDisconnect:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE sessions SET ended_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), session_id)
            )
            conn.commit()
        finally:
            conn.close()
