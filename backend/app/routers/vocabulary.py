"""
Vocabulary router — read-only lookup of the shared lexicon that both
Pipeline A (avatar playback) and Pipeline B (recognition training labels)
are built on. Seeding/editing happens via scripts/seed_vocabulary.py, not
through this API.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from app.database.local_db import get_connection
from app.models.vocabulary import VocabularyItem, VocabularyListResponse

router = APIRouter(prefix="/vocabulary", tags=["vocabulary"])


@router.get("/health")
async def vocabulary_health():
    return {"status": "ok", "service": "vocabulary"}


@router.get("", response_model=VocabularyListResponse)
async def list_vocabulary(category: Optional[str] = Query(default=None)):
    """
    List all vocabulary entries, optionally filtered by category.
    `has_clip` tells the frontend whether a sign_clips row (and therefore
    an avatar sequence) exists yet for that word.
    """
    conn = get_connection()
    try:
        if category:
            cursor = conn.execute(
                """
                SELECT v.id, v.word_en, v.word_hi, v.gloss_tag, v.category,
                       CASE WHEN sc.id IS NULL THEN 0 ELSE 1 END AS has_clip
                FROM vocabulary v
                LEFT JOIN sign_clips sc ON sc.vocabulary_id = v.id
                WHERE v.category = ?
                ORDER BY v.word_en
                """,
                (category,)
            )
        else:
            cursor = conn.execute(
                """
                SELECT v.id, v.word_en, v.word_hi, v.gloss_tag, v.category,
                       CASE WHEN sc.id IS NULL THEN 0 ELSE 1 END AS has_clip
                FROM vocabulary v
                LEFT JOIN sign_clips sc ON sc.vocabulary_id = v.id
                ORDER BY v.word_en
                """
            )
        rows = cursor.fetchall()
        words = [
            VocabularyItem(
                id=r[0], word_en=r[1], word_hi=r[2], gloss_tag=r[3],
                category=r[4], has_clip=bool(r[5])
            )
            for r in rows
        ]
        return VocabularyListResponse(words=words, count=len(words))
    finally:
        conn.close()


@router.get("/{vocab_id}", response_model=VocabularyItem)
async def get_vocabulary_item(vocab_id: int):
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT v.id, v.word_en, v.word_hi, v.gloss_tag, v.category,
                   CASE WHEN sc.id IS NULL THEN 0 ELSE 1 END AS has_clip
            FROM vocabulary v
            LEFT JOIN sign_clips sc ON sc.vocabulary_id = v.id
            WHERE v.id = ?
            """,
            (vocab_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Vocabulary id {vocab_id} not found")
        return VocabularyItem(
            id=row[0], word_en=row[1], word_hi=row[2], gloss_tag=row[3],
            category=row[4], has_clip=bool(row[5])
        )
    finally:
        conn.close()
