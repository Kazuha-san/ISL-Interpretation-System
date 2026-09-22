"""
scripts/seed_quick_phrases.py

Seeds the quick_phrases table with pre-computed gloss JSON for common
counter-staff phrases. Runs convert_to_gloss_smart() once per phrase
to compute and store the gloss, so selection at runtime is instant.

Run from the backend/ directory:
    python -m scripts.seed_quick_phrases
"""

import json
import sys
from pathlib import Path
from typing import List, Tuple

from app.database.local_db import get_connection, init_db
from app.services.gloss import convert_to_gloss_smart
from app.config import settings


# Sample counter-conversation phrases grouped by context
# Format: (context, display_text)
PHRASES: List[Tuple[str, str]] = [
    # Identity context
    ("identity", "What is your name?"),
    ("identity", "What is your age?"),
    ("identity", "What is your address?"),
    ("identity", "Please show your ID card"),
    ("identity", "What is your date of birth?"),
    ("identity", "Are you male or female?"),
    
    # General/Welcome phrases
    ("general", "Please wait"),
    ("general", "Thank you"),
    ("general", "What can I help you with?"),
    ("general", "Welcome"),
    ("general", "How may I help you?"),
    ("general", "Please follow me"),
    
    # Banking context
    ("banking", "What type of account do you have?"),
    ("banking", "Please fill out this form"),
    ("banking", "Please wait while we verify your documents"),
    ("banking", "Your transaction is complete"),
    
    # Health context
    ("health", "Where are you feeling pain?"),
    ("health", "When did you start feeling unwell?"),
    ("health", "Please follow the treatment plan"),
    
    # Education context
    ("education", "Which class do you want to join?"),
    ("education", "Please submit your application"),
]


async def seed_phrases() -> None:
    """Seed the quick_phrases table with sample phrases."""
    conn = get_connection()
    inserted = 0
    skipped = 0

    try:
        for context, display_text in PHRASES:
            # Run the phrase through convert_to_gloss_smart to compute gloss JSON
            result = await convert_to_gloss_smart(
                transcript=display_text,
                context=context,
                language="en"  # Using English for demo; can be "hi" for Hindi
            )
            
            # Extract just the gloss_result structure
            gloss_result = {
                "gloss": result.get("gloss", []),
                "tokens": result.get("tokens", [])
            }
            gloss_json = json.dumps(gloss_result)
            
            # Insert into quick_phrases
            cursor = conn.execute(
                """
                INSERT INTO quick_phrases 
                    (kiosk_id, context, display_text, gloss_json, sort_order, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    settings.KIOSK_ID,
                    context,
                    display_text,
                    gloss_json,
                    inserted,  # sort_order = insertion order
                    "2024-01-01T00:00:00+00:00"  # Fixed timestamp for seeded data
                )
            )
            
            if cursor.rowcount > 0:
                inserted += 1
                print(f"  ✓ [{context}] {display_text}")
            else:
                skipped += 1
                print(f"  ✗ [{context}] {display_text} (already exists)")
            
            conn.commit()
            
    finally:
        conn.close()

    print(f"\nDone. Inserted {inserted} phrase(s), skipped {skipped} "
          f"(already existed).")


async def verify() -> None:
    """Verify the seeded data."""
    conn = get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM quick_phrases").fetchone()[0]
        print(f"\nTotal quick_phrases in database: {count}")
        
        # Count by context
        cursor = conn.execute(
            """
            SELECT context, COUNT(*) as count 
            FROM quick_phrases 
            GROUP BY context 
            ORDER BY context
            """
        ).fetchall()
        
        if cursor:
            print("\nPhrases by context:")
            for row in cursor:
                print(f"  {row[0]}: {row[1]}")
                
    finally:
        conn.close()


async def main() -> None:
    """Main entry point."""
    print("Initializing database...")
    init_db()
    
    print("\nSeeding quick phrases...")
    await seed_phrases()
    
    print("\nVerifying data...")
    await verify()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
