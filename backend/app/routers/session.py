from fastapi import APIRouter

router = APIRouter(prefix="/session", tags=["session"])


@router.get("/health")
async def session_health():
    return {"status": "ok", "service": "session"}
