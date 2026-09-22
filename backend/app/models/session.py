"""
Pydantic models for session data (app/routers/session.py).

A "session" is one interaction at the kiosk/counter, in either direction:
  A = hearing -> Deaf (avatar signing)
  B = Deaf -> hearing (sign recognition)
"""
from pydantic import BaseModel
from typing import Literal, Optional


class SessionCreate(BaseModel):
    direction: Literal["A", "B"]
    kiosk_id: Optional[str] = None  # defaults to settings.KIOSK_ID if omitted


class SessionResponse(BaseModel):
    id: int
    kiosk_id: str
    started_at: str
    ended_at: Optional[str] = None
    direction: Literal["A", "B"]


class SessionEndRequest(BaseModel):
    session_id: int
