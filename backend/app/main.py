from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.local_db import init_db
from app.routers import translate, vocabulary, qna, session, sync


app = FastAPI(
    title="ISL Kiosk Translation API",
    description="API for Indian Sign Language kiosk translation services",
    version="0.1.0",
)

# CORS middleware for Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    """Initialize database on startup."""
    await init_db()


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}


# Mount routers
app.include_router(translate.router)
app.include_router(vocabulary.router)
app.include_router(qna.router)
app.include_router(session.router)
app.include_router(sync.router)
