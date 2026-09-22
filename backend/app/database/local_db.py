"""
app/database/local_db.py

Creates the local SQLite connection and all 7 tables on startup if they
do not already exist. WAL mode is enabled per NFR2 (resilience to
incomplete writes on unexpected power loss at a kiosk).

Call `init_db()` once from main.py's startup event.
Call `get_connection()` anywhere else that needs a db handle.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Literal, List

from ..config import settings

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS vocabulary (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    word_en     TEXT NOT NULL,
    word_hi     TEXT,
    gloss_tag   TEXT NOT NULL UNIQUE,
    category    TEXT,
    clip_id     INTEGER REFERENCES sign_clips(id)
);

CREATE TABLE IF NOT EXISTS sign_clips (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    vocabulary_id       INTEGER REFERENCES vocabulary(id),
    video_url           TEXT,
    keypoint_json_path  TEXT,
    duration_ms         INTEGER,
    signer_ref          TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kiosk_id    TEXT,
    started_at  TEXT,
    ended_at    TEXT,
    direction   TEXT CHECK(direction IN ('A','B'))
);

CREATE TABLE IF NOT EXISTS session_logs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     INTEGER REFERENCES sessions(id),
    input_text     TEXT,
    gloss_output   TEXT,
    fallback_used  INTEGER DEFAULT 0,
    timestamp      TEXT
);

CREATE TABLE IF NOT EXISTS qna_packs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id      TEXT,
    title               TEXT,
    created_at          TEXT,
    assigned_kiosk_ids  TEXT
);

CREATE TABLE IF NOT EXISTS qna_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_id         INTEGER REFERENCES qna_packs(id),
    question_text   TEXT,
    answer_text     TEXT,
    gloss_json      TEXT,
    clip_sequence   TEXT,
    review_status   TEXT CHECK(review_status IN
                    ('draft','pending_review','approved')),
    reviewed_by     TEXT
);

CREATE TABLE IF NOT EXISTS staff_progress (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id          TEXT,
    vocabulary_id     INTEGER REFERENCES vocabulary(id),
    correct_count     INTEGER DEFAULT 0,
    last_reviewed_at  TEXT
);

CREATE TABLE IF NOT EXISTS resolved_phrases_cache (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    normalized_input  TEXT NOT NULL,
    context           TEXT NOT NULL,
    gloss_json        TEXT NOT NULL,
    source            TEXT NOT NULL CHECK(source IN ('groq','local_rule_engine')),
    review_status     TEXT NOT NULL DEFAULT 'pending_review'
                      CHECK(review_status IN ('pending_review','approved','rejected')),
    hit_count         INTEGER DEFAULT 1,
    created_at        TEXT NOT NULL,
    last_used_at      TEXT NOT NULL,
    UNIQUE(normalized_input, context)
);

CREATE TABLE IF NOT EXISTS quick_phrases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kiosk_id        TEXT NOT NULL,
    context         TEXT NOT NULL,
    display_text    TEXT NOT NULL,
    gloss_json      TEXT NOT NULL,
    sort_order      INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL
);

-- Pipeline B (Deaf -> hearing): one row per recognized sign sequence.
-- Populated by app/services/recognition.py. Used both to show the signer
-- what was recognized before it's spoken, and later as a correction /
-- training-data queue once real model output starts flowing in.
CREATE TABLE IF NOT EXISTS recognition_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER REFERENCES sessions(id),
    gloss_sequence  TEXT,
    sentence_text   TEXT,
    confidence      REAL,
    confirmed       INTEGER DEFAULT 0,
    corrected_text  TEXT,
    created_at      TEXT NOT NULL
);
"""


def get_connection() -> sqlite3.Connection:
    """
    Opens a new connection to the local SQLite file. Each caller should
    open, use, and close its own connection (or use a context manager) —
    do not share one long-lived connection across requests.
    """
    db_path = Path(settings.LOCAL_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    """
    Creates all tables if they don't exist. Safe to call on every
    startup — CREATE TABLE IF NOT EXISTS is idempotent and never drops
    or alters existing data.
    
    Also initializes sync_meta table used for cloud sync tracking.
    """
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


# --- Cache helper functions ---

def cache_lookup(
    normalized_input: str,
    context: str
) -> Optional[dict]:
    """
    Look up a cached result by normalized input and context.
    
    Only returns entries with review_status='approved'.
    
    Returns:
        Dict with gloss_json, hit_count, last_used_at, or None if not found
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT gloss_json, hit_count, last_used_at
            FROM resolved_phrases_cache
            WHERE normalized_input = ? AND context = ? AND review_status = 'approved'
            """,
            (normalized_input, context)
        )
        row = cursor.fetchone()
        if row:
            return {
                "gloss_json": row[0],
                "hit_count": row[1],
                "last_used_at": row[2]
            }
        return None
    finally:
        conn.close()


def cache_upsert(
    normalized_input: str,
    context: str,
    gloss_json: str,
    source: Literal["groq", "local_rule_engine"]
) -> None:
    """
    Upsert a cache entry. If the entry exists, increment hit_count and update last_used_at.
    If new, insert with review_status='pending_review'.
    
    Args:
        normalized_input: Normalized input text
        context: Session context (general, banking, health, identity, education)
        gloss_json: JSON string of the gloss result
        source: Source of the result ('groq' or 'local_rule_engine')
    """
    conn = get_connection()
    try:
        # Check if entry exists
        cursor = conn.execute(
            """
            SELECT id, hit_count FROM resolved_phrases_cache
            WHERE normalized_input = ? AND context = ? AND review_status != 'rejected'
            """,
            (normalized_input, context)
        )
        existing = cursor.fetchone()
        
        timestamp = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
        
        if existing:
            # Update existing entry
            conn.execute(
                """
                UPDATE resolved_phrases_cache
                SET hit_count = hit_count + 1,
                    last_used_at = ?
                WHERE id = ?
                """,
                (timestamp, existing[0])
            )
        else:
            # Insert new entry
            conn.execute(
                """
                INSERT INTO resolved_phrases_cache (
                    normalized_input, context, gloss_json, source,
                    review_status, hit_count, created_at, last_used_at
                ) VALUES (?, ?, ?, ?, 'pending_review', 1, ?, ?)
                """,
                (normalized_input, context, gloss_json, source, timestamp, timestamp)
            )
        
        conn.commit()
    finally:
        conn.close()


def cache_approve(cache_id: int) -> bool:
    """
    Mark a cache entry as approved.
    
    Returns:
        True if a row was updated, False if no such entry exists
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            UPDATE resolved_phrases_cache
            SET review_status = 'approved'
            WHERE id = ? AND review_status = 'pending_review'
            """,
            (cache_id,)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def cache_reject(cache_id: int) -> bool:
    """
    Mark a cache entry as rejected.
    
    Returns:
        True if a row was updated, False if no such entry exists
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            UPDATE resolved_phrases_cache
            SET review_status = 'rejected'
            WHERE id = ? AND review_status = 'pending_review'
            """,
            (cache_id,)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def cache_get_pending() -> List[dict]:
    """
    Get all pending_review cache entries for review.
    
    Returns:
        List of dicts with id, normalized_input, context, source, hit_count, created_at
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT id, normalized_input, context, source, hit_count, created_at
            FROM resolved_phrases_cache
            WHERE review_status = 'pending_review'
            ORDER BY created_at ASC
            """
        )
        return [
            {
                "id": row[0],
                "normalized_input": row[1],
                "context": row[2],
                "source": row[3],
                "hit_count": row[4],
                "created_at": row[5]
            }
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


if __name__ == "__main__":
    # Manual run: `python -m app.database.local_db` to create/verify
    # the schema without starting the full FastAPI app.
    init_db()
    print(f"SQLite schema verified at {settings.LOCAL_DB_PATH}")


# --- Quick phrases helper functions ---

def get_quick_phrases_db(context: str, kiosk_id: str = None) -> List[dict]:
    """
    Get all quick phrases for a context, ordered by sort_order.
    
    Args:
        context: Session context (general, banking, health, identity, education)
        kiosk_id: Optional kiosk filter (defaults to settings.KIOSK_ID)
        
    Returns:
        List of dicts with id, display_text, context
    """
    conn = get_connection()
    try:
        if kiosk_id is None:
            kiosk_id = settings.KIOSK_ID
            
        cursor = conn.execute(
            """
            SELECT id, display_text, context
            FROM quick_phrases
            WHERE kiosk_id = ? AND context = ?
            ORDER BY sort_order ASC
            """,
            (kiosk_id, context)
        )
        return [
            {
                "id": row[0],
                "display_text": row[1],
                "context": row[2]
            }
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


def get_quick_phrase_by_id_db(phrase_id: int) -> Optional[dict]:
    """
    Get a single quick phrase by ID.
    
    Args:
        phrase_id: Quick phrases table ID
        
    Returns:
        Dict with all fields including gloss_json, or None if not found
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT id, kiosk_id, context, display_text, gloss_json, sort_order, created_at
            FROM quick_phrases
            WHERE id = ?
            """,
            (phrase_id,)
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "kiosk_id": row[1],
                "context": row[2],
                "display_text": row[3],
                "gloss_json": row[4],
                "sort_order": row[5],
                "created_at": row[6]
            }
        return None
    finally:
        conn.close()


def insert_quick_phrase(kiosk_id: str, context: str, display_text: str, gloss_json: str, sort_order: int = 0) -> int:
    """
    Insert a new quick phrase.
    
    Args:
        kiosk_id: Kiosk identifier
        context: Session context
        display_text: Text to display for staff selection
        gloss_json: Pre-computed gloss JSON string
        sort_order: Order for display (lower = shown first)
        
    Returns:
        The ID of the inserted row
    """
    conn = get_connection()
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            """
            INSERT INTO quick_phrases (kiosk_id, context, display_text, gloss_json, sort_order, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (kiosk_id, context, display_text, gloss_json, sort_order, timestamp)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def delete_quick_phrase(phrase_id: int) -> bool:
    """
    Delete a quick phrase by ID.
    
    Returns:
        True if a row was deleted, False if not found
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            DELETE FROM quick_phrases
            WHERE id = ?
            """,
            (phrase_id,)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# --- Pipeline B: recognition session helpers ---

def insert_recognition_session(
    session_id: int,
    gloss_sequence: List[str],
    sentence_text: str,
    confidence: Optional[float]
) -> int:
    """
    Store one recognized sign->text result for confirmation/display.

    Args:
        session_id: FK into sessions (direction='B')
        gloss_sequence: list of recognized gloss tags, in order
        sentence_text: assembled sentence text shown to the signer for confirmation
        confidence: model confidence 0.0-1.0, or None if unavailable

    Returns:
        The id of the inserted recognition_sessions row
    """
    import json as _json
    conn = get_connection()
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            """
            INSERT INTO recognition_sessions
                (session_id, gloss_sequence, sentence_text, confidence, confirmed, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (session_id, _json.dumps(gloss_sequence), sentence_text, confidence, timestamp)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def confirm_recognition_session(recognition_id: int, corrected_text: Optional[str] = None) -> bool:
    """
    Mark a recognized sentence as confirmed by the signer before it's spoken.
    If the signer edited it, pass the corrected text — this is the row that
    later becomes training/eval data for the recognizer.

    Returns:
        True if a row was updated, False if not found
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            UPDATE recognition_sessions
            SET confirmed = 1, corrected_text = ?
            WHERE id = ?
            """,
            (corrected_text, recognition_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
