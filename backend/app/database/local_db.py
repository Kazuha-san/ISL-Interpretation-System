"""
app/database/local_db.py

Creates the local SQLite connection and all 7 tables on startup if they
do not already exist. WAL mode is enabled per NFR2 (resilience to
incomplete writes on unexpected power loss at a kiosk).

Call `init_db()` once from main.py's startup event.
Call `get_connection()` anywhere else that needs a db handle.
"""

import sqlite3
from pathlib import Path

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
    Creates all 7 tables if they don't exist. Safe to call on every
    startup — CREATE TABLE IF NOT EXISTS is idempotent and never drops
    or alters existing data.
    """
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    # Manual run: `python -m app.database.local_db` to create/verify
    # the schema without starting the full FastAPI app.
    init_db()
    print(f"SQLite schema verified at {settings.LOCAL_DB_PATH}")
