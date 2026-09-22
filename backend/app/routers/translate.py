"""
Translate router for ISL gloss conversion.
"""
import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional, List, Dict, Any
from app.services.gloss import convert_to_gloss_smart
from app.services.retrieval import resolve_tokens_to_sequences
from app.database.local_db import (
    get_connection,
    get_quick_phrases_db,
    get_quick_phrase_by_id_db
)
from app.config import settings


class TranslateRequest(BaseModel):
    """Request model for translation."""
    transcript: str
    context: Literal["general", "banking", "health", "identity", "education"] = "general"
    language: Literal["en", "hi"] = "en"


class TranslateResponse(BaseModel):
    """Response model for translation."""
    gloss: List[str]
    tokens: List[dict]
    sequences: List[Optional[dict]]
    fallbacks: List[str]
    transcript: str
    context: str
    session_id: str
    # Additional fields for transparency/debugging (additive only)
    source: Optional[str] = None
    confidence: Optional[float] = None
    was_online: Optional[bool] = None


router = APIRouter(prefix="/translate", tags=["translate"])


@router.get("/health")
async def translate_health():
    """Health check endpoint."""
    return {"status": "ok", "service": "translate"}


@router.post("/forward", response_model=TranslateResponse)
async def translate_forward(request: TranslateRequest):
    """
    Convert a transcript to ISL gloss and resolve to playable avatar sequences.
    
    This endpoint uses a smart resolution order:
    1. Exact match in resolved_phrases_cache (approved only)
    2. Local rule engine, if confidence HIGH -> use directly
    3. Groq, if reachable -> use its result, cache it (pending_review)
    4. Local rule engine best-effort (if MEDIUM/LOW confidence and Groq unreachable)
    5. Full fingerspell fallback (if local confidence was LOW and Groq unreachable)
    
    The context parameter influences vocabulary preference when multiple
    valid options exist.
    
    Returns gloss tokens, resolved sequences for avatar playback, and
    a list of fallbacks for tokens that couldn't be resolved to clips.
    
    Also creates a session and logs the interaction to session_logs for
    analytics and sync purposes.
    
    Response includes additional debug fields:
    - source: where the result came from 
      ("cache" | "local_rule_engine" | "groq" | "fingerspell_fallback" | "quick_phrase")
    - confidence: local engine confidence (0.0-1.0) if available
    - was_online: whether Groq was reachable during resolution
    """
    try:
        # Step 1: Create a new session (one-shot per request)
        conn = get_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO sessions (kiosk_id, started_at, direction)
                VALUES (?, ?, ?)
                """,
                (settings.KIOSK_ID, datetime.now(timezone.utc).isoformat(), "A")
            )
            session_id = str(cursor.lastrowid)
            conn.commit()
        finally:
            conn.close()
        
        # Step 2: Convert transcript to gloss using smart engine
        result = await convert_to_gloss_smart(
            transcript=request.transcript,
            context=request.context,
            language=request.language
        )
        
        # Extract the core gloss result (gloss and tokens are always present)
        gloss_result = {
            "gloss": result.get("gloss", []),
            "tokens": result.get("tokens", [])
        }
        
        # Step 3: Resolve tokens to sequences
        sequence_result = await resolve_tokens_to_sequences(gloss_result["tokens"])
        
        # Step 4: Log to session_logs
        fallback_used = 1 if sequence_result["fallbacks"] else 0
        gloss_output = json.dumps(gloss_result)
        timestamp = datetime.now(timezone.utc).isoformat()
        
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO session_logs (session_id, input_text, gloss_output, fallback_used, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, request.transcript, gloss_output, fallback_used, timestamp)
            )
            conn.commit()
        finally:
            conn.close()
        
        return TranslateResponse(
            gloss=gloss_result["gloss"],
            tokens=gloss_result["tokens"],
            sequences=sequence_result["sequences"],
            fallbacks=sequence_result["fallbacks"],
            transcript=request.transcript,
            context=request.context,
            session_id=session_id,
            source=result.get("source"),
            confidence=result.get("confidence"),
            was_online=result.get("was_online")
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")


@router.get("/quick-phrases", response_model=Dict[str, List[dict]])
async def get_quick_phrases(context: str = "general"):
    """
    Get all quick phrases for a context.
    
    Returns a light-weight list of phrases with id, display_text, and context.
    The full gloss_json is not included - fetch it via POST /quick-phrase/{id}
    when a phrase is selected.
    """
    try:
        phrases = get_quick_phrases_db(context)
        return {"phrases": phrases}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch quick phrases: {str(e)}")


@router.post("/quick-phrase/{phrase_id}", response_model=TranslateResponse)
async def use_quick_phrase(phrase_id: int):
    """
    Use a quick phrase by ID.
    
    Looks up the pre-computed gloss JSON, resolves tokens to sequences,
    creates a session log, and returns the same TranslateResponse shape
    as /translate/forward.
    
    Sets source="quick_phrase" to indicate this was a pre-computed phrase.
    """
    try:
        # Step 1: Look up the quick phrase
        phrase = get_quick_phrase_by_id_db(phrase_id)
        if not phrase:
            raise HTTPException(status_code=404, detail=f"Quick phrase with ID {phrase_id} not found")
        
        # Step 2: Parse gloss JSON
        try:
            gloss_result = json.loads(phrase["gloss_json"])
            if not isinstance(gloss_result, dict) or "gloss" not in gloss_result or "tokens" not in gloss_result:
                raise ValueError("Invalid gloss_json format in quick phrase")
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f"Malformed gloss_json in quick phrase: {e}")
        
        # Step 3: Resolve tokens to sequences
        sequence_result = await resolve_tokens_to_sequences(gloss_result["tokens"])
        
        # Step 4: Create a new session (same pattern as translate_forward)
        conn = get_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO sessions (kiosk_id, started_at, direction)
                VALUES (?, ?, ?)
                """,
                (settings.KIOSK_ID, datetime.now(timezone.utc).isoformat(), "A")
            )
            session_id = str(cursor.lastrowid)
            conn.commit()
        finally:
            conn.close()
        
        # Step 5: Log to session_logs
        fallback_used = 1 if sequence_result["fallbacks"] else 0
        gloss_output = json.dumps(gloss_result)
        timestamp = datetime.now(timezone.utc).isoformat()
        
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO session_logs (session_id, input_text, gloss_output, fallback_used, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, phrase["display_text"], gloss_output, fallback_used, timestamp)
            )
            conn.commit()
        finally:
            conn.close()
        
        return TranslateResponse(
            gloss=gloss_result["gloss"],
            tokens=gloss_result["tokens"],
            sequences=sequence_result["sequences"],
            fallbacks=sequence_result["fallbacks"],
            transcript=phrase["display_text"],
            context=phrase["context"],
            session_id=session_id,
            source="quick_phrase",
            confidence=None,
            was_online=False
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to use quick phrase: {str(e)}")


@router.get("/test")
async def translate_test():
    """Test endpoint with a simple example."""
    test_transcript = "What is your name?"
    test_context = "identity"
    
    try:
        result = await convert_to_gloss_smart(test_transcript, test_context)
        return {
            "test_transcript": test_transcript,
            "test_context": test_context,
            "result": result,
            "note": "This requires a valid GROQ_API_KEY to work"
        }
    except Exception as e:
        return {
            "test_transcript": test_transcript,
            "test_context": test_context,
            "error": str(e),
            "note": "GROQ_API_KEY is not set or invalid"
        }
