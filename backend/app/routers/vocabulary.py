from fastapi import APIRouter

router = APIRouter(prefix="/vocabulary", tags=["vocabulary"])


@router.get("/health")
async def vocabulary_health():
    return {"status": "ok", "service": "vocabulary"}
