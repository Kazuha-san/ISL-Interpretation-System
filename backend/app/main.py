from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database.local_db import init_db
from app.routers import translate, vocabulary, qna, session, cache_admin, recognize


app = FastAPI(
    title="ISL Interpreter API",
    description=(
        "Backend for a two-way ISL interpreter for general workplaces. "
        "Pipeline A (/translate) converts speech/text to ISL gloss for "
        "avatar playback. Pipeline B (/recognize) is the Deaf-to-hearing "
        "path — camera-based recognition, streamed over WebSocket."
    ),
    version="0.5.0",
)

# CORS middleware for Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    """Initialize database on startup."""
    init_db()


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.5.0"}


# Mount routers
app.include_router(translate.router)     # Pipeline A: hearing -> Deaf
app.include_router(recognize.router)     # Pipeline B: Deaf -> hearing
app.include_router(vocabulary.router)
app.include_router(qna.router)
app.include_router(session.router)
app.include_router(cache_admin.router)
