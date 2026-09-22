"""
Admin endpoints for managing resolved_phrases_cache.

Provides simple curl-able endpoints for:
- Listing pending review entries
- Approving entries
- Rejecting entries
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from app.database.local_db import (
    cache_get_pending,
    cache_approve,
    cache_reject,
    get_connection,
)

router = APIRouter(prefix="/admin/cache", tags=["cache_admin"])


class CacheEntry(BaseModel):
    id: int
    normalized_input: str
    context: str
    source: str
    hit_count: int
    created_at: str


class CacheApprovalResult(BaseModel):
    success: bool
    message: str


@router.get("/pending", response_model=List[CacheEntry])
async def get_pending_entries():
    """
    Get all entries that are pending review.
    
    Returns:
        List of cache entries with id, normalized_input, context, source, hit_count, created_at
    """
    try:
        entries = cache_get_pending()
        return entries
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch pending entries: {str(e)}")


@router.post("/cache/{cache_id}/approve", response_model=CacheApprovalResult)
async def approve_entry(cache_id: int):
    """
    Approve a cache entry, making it eligible for cache hits.
    
    Args:
        cache_id: ID of the cache entry to approve
        
    Returns:
        {success: bool, message: str}
    """
    try:
        success = cache_approve(cache_id)
        if success:
            return CacheApprovalResult(success=True, message="Entry approved successfully")
        else:
            raise HTTPException(status_code=404, detail=f"No pending entry found with id={cache_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to approve entry: {str(e)}")


@router.post("/cache/{cache_id}/reject", response_model=CacheApprovalResult)
async def reject_entry(cache_id: int):
    """
    Reject a cache entry.
    
    Args:
        cache_id: ID of the cache entry to reject
        
    Returns:
        {success: bool, message: str}
    """
    try:
        success = cache_reject(cache_id)
        if success:
            return CacheApprovalResult(success=True, message="Entry rejected successfully")
        else:
            raise HTTPException(status_code=404, detail=f"No pending entry found with id={cache_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reject entry: {str(e)}")
