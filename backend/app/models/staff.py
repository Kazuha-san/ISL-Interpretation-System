"""
Pydantic models for staff progress data (app/routers/session.py's
staff-facing endpoints, or a future staff router).

Tracks which vocabulary a counter staff member has practiced, so the
UI can show them a "words you haven't tried yet" list. Not authentication —
staff_id is just a self-chosen identifier for now, no login system.
"""
from pydantic import BaseModel
from typing import Optional


class StaffProgressItem(BaseModel):
    vocabulary_id: int
    gloss_tag: str
    correct_count: int
    last_reviewed_at: Optional[str] = None


class StaffProgressResponse(BaseModel):
    staff_id: str
    items: list[StaffProgressItem]
