"""
Q&A router for ISL kiosk translation system.
Provides endpoints for managing and retrieving Q&A packs.
"""
import json
from fastapi import APIRouter, HTTPException
from app.config import settings
from app.models.qna import QnaApprovedResponse, QnaPackResponse, QnaItemResponse
from app.database.local_db import get_connection

router = APIRouter(prefix="/qna", tags=["qna"])


@router.get("/health")
async def qna_health():
    return {"status": "ok", "service": "qna"}


@router.get("/approved", response_model=QnaApprovedResponse)
async def get_approved_qna():
    """
    Get all approved Q&A items assigned to this kiosk.
    
    Reads the kiosk's assigned pack IDs from qna_packs.assigned_kiosk_ids
    (stored as JSON-encoded TEXT), fetches approved items from those packs,
    and returns them structured for frontend quick-answer buttons.
    """
    conn = get_connection()
    try:
        # Get all packs assigned to this kiosk
        cursor = conn.execute("SELECT id, title, assigned_kiosk_ids FROM qna_packs")
        packs = cursor.fetchall()
        
        assigned_packs = []
        for pack_id, pack_title, assigned_kiosk_ids_str in packs:
            # Parse the JSON string of assigned kiosk IDs
            try:
                assigned_kiosk_ids = json.loads(assigned_kiosk_ids_str)
            except (json.JSONDecodeError, TypeError):
                assigned_kiosk_ids = []
            
            # Check if this kiosk is in the assigned list
            if settings.KIOSK_ID in assigned_kiosk_ids:
                # Get approved items for this pack
                item_cursor = conn.execute(
                    """
                    SELECT id, question_text, answer_text, gloss_json, clip_sequence
                    FROM qna_items
                    WHERE pack_id = ? AND review_status = 'approved'
                    ORDER BY id
                    """,
                    (pack_id,)
                )
                items = []
                for row in item_cursor.fetchall():
                    # Parse JSON strings
                    try:
                        gloss_json = json.loads(row[3]) if row[3] else {}
                    except (json.JSONDecodeError, TypeError):
                        gloss_json = {}
                    try:
                        clip_sequence = json.loads(row[4]) if row[4] else {}
                    except (json.JSONDecodeError, TypeError):
                        clip_sequence = {}
                    
                    items.append(QnaItemResponse(
                        id=row[0],
                        question=row[1],
                        answer=row[2],
                        gloss_json=gloss_json if gloss_json else None,
                        clip_sequence=clip_sequence if clip_sequence else None
                    ))
                
                assigned_packs.append(QnaPackResponse(
                    id=pack_id,
                    title=pack_title,
                    items=items
                ))
        
        return QnaApprovedResponse(packs=assigned_packs)
        
    finally:
        conn.close()
