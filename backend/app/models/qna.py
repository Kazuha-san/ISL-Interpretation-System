"""
Pydantic models for Q&A data.
"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class QnaItemResponse(BaseModel):
    """Single Q&A item response."""
    id: int
    question: str
    answer: str
    gloss_json: Optional[Dict[str, Any]]
    clip_sequence: Optional[Dict[str, Any]]


class QnaPackResponse(BaseModel):
    """Q&A pack with its items."""
    id: int
    title: str
    items: List[QnaItemResponse]


class QnaApprovedResponse(BaseModel):
    """Response for approved Q&A items endpoint."""
    packs: List[QnaPackResponse]
