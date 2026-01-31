from fastapi import APIRouter, Query

from app.schemas.shorts import ShortsResponse
from app.services.youtube_shorts_service import get_shorts_for_keyword, get_shorts_of_the_hour

router = APIRouter(prefix="/shorts", tags=["shorts"])


@router.get("", response_model=ShortsResponse)
async def shorts(
    limit: int = Query(8, ge=1, le=16),
    keyword: str | None = Query(None),
):
    if keyword:
        return await get_shorts_for_keyword(keyword=keyword, limit=limit)
    return await get_shorts_of_the_hour(limit=limit)
