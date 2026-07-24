from fastapi import APIRouter

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/health")
async def sync_health():
    return {"status": "ok", "service": "sync"}
