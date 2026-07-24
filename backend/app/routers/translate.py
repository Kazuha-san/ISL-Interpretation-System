"""
Translate router for ISL gloss conversion.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional
from app.services.gloss import convert_to_gloss


class TranslateRequest(BaseModel):
    """Request model for translation."""
    transcript: str
    context: Literal["general", "banking", "health", "identity"] = "general"
    session_id: Optional[str] = None


class TranslateResponse(BaseModel):
    """Response model for translation."""
    gloss: list[str]
    tokens: list[dict]
    transcript: str
    context: str


router = APIRouter(prefix="/translate", tags=["translate"])


@router.get("/health")
async def translate_health():
    """Health check endpoint."""
    return {"status": "ok", "service": "translate"}


@router.post("/forward", response_model=TranslateResponse)
async def translate_forward(request: TranslateRequest):
    """
    Convert a transcript to ISL gloss.
    
    This endpoint uses the Groq API with the system prompt defined in 
    gloss_prompt.md to convert Hindi/English transcripts to ISL gloss.
    
    The context parameter influences vocabulary preference when multiple
    valid options exist.
    """
    try:
        result = await convert_to_gloss(
            transcript=request.transcript,
            context=request.context
        )
        
        return TranslateResponse(
            gloss=result["gloss"],
            tokens=result["tokens"],
            transcript=request.transcript,
            context=request.context
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")


@router.get("/test")
async def translate_test():
    """Test endpoint with a simple example."""
    test_transcript = "What is your name?"
    test_context = "identity"
    
    try:
        result = await convert_to_gloss(test_transcript, test_context)
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
