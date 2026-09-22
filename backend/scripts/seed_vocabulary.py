"""
scripts/seed_vocabulary.py

Reads assets/vocabulary/vocab.csv and seeds the SQLite `vocabulary`
table. Safe to re-run: uses INSERT OR IGNORE keyed on the UNIQUE
gloss_tag column, so re-running after adding new words to the CSV
only inserts the new rows and leaves existing ones (and their
sign_clips links) untouched.

Run from the backend/ directory:
    python -m scripts.seed_vocabulary
"""

import csv
import sys
from pathlib import Path

# Adjust this import path if your package layout differs
from app.database.local_db import get_connection, init_db

CSV_PATH = Path("assets/vocabulary/vocab.csv")

REQUIRED_COLUMNS = {"word_en", "word_hi", "gloss_tag", "category", "clip_filename"}


def load_rows(csv_path: Path) -> list[dict]:
    if not csv_path.exists():
        print(f"ERROR: {csv_path} not found.")
        sys.exit(1)

    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)

        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            print(f"ERROR: CSV is missing required columns: {missing}")
            sys.exit(1)

        rows = list(reader)

    if not rows:
        print(f"ERROR: {csv_path} has no data rows.")
        sys.exit(1)

    return rows


def seed(rows: list[dict]) -> None:
    conn = get_connection()
    inserted = 0
    skipped = 0

    try:
        for row in rows:
            gloss_tag = row["gloss_tag"].strip()
            word_en = row["word_en"].strip()
            word_hi = row["word_hi"].strip()
            category = row["category"].strip()

            if not gloss_tag or not word_en:
                print(f"WARNING: skipping row with missing gloss_tag/word_en: {row}")
                skipped += 1
                continue

            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO vocabulary
                    (word_en, word_hi, gloss_tag, category)
                VALUES (?, ?, ?, ?)
                """,
                (word_en, word_hi, gloss_tag, category),
            )
            if cursor.rowcount > 0:
                inserted += 1
            else:
                skipped += 1

        conn.commit()
    finally:
        conn.close()

    print(f"Done. Inserted {inserted} new word(s), skipped {skipped} "
          f"(already existed or invalid).")


def verify() -> None:
    conn = get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM vocabulary").fetchone()[0]
        print(f"Current vocabulary table row count: {count}")

        dupes = conn.execute(
            """
            SELECT gloss_tag, COUNT(*) c FROM vocabulary
            GROUP BY gloss_tag HAVING c > 1
            """
        ).fetchall()
        if dupes:
            print(f"WARNING: duplicate gloss_tags found (should be impossible "
                  f"due to UNIQUE constraint): {dupes}")
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()  # ensure tables exist before seeding
    rows = load_rows(CSV_PATH)
    seed(rows)
    verify()
