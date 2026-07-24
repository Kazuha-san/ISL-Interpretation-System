from fastapi import APIRouter

router = APIRouter(prefix="/qna", tags=["qna"])


@router.get("/health")
async def qna_health():
    return {"status": "ok", "service": "qna"}
