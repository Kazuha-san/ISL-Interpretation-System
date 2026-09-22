"""
Pydantic models for vocabulary data (app/routers/vocabulary.py).
"""
from pydantic import BaseModel
from typing import Optional


class VocabularyItem(BaseModel):
    """One vocabulary table row, as returned to the frontend."""
    id: int
    word_en: str
    word_hi: Optional[str] = None
    gloss_tag: str
    category: Optional[str] = None
    has_clip: bool = False


class VocabularyListResponse(BaseModel):
    words: list[VocabularyItem]
    count: int
