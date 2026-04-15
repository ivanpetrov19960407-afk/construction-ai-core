"""Web UI routes."""

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/web", include_in_schema=False)
async def web_index() -> FileResponse:
    """Serve web mini app index file."""
    return FileResponse("web/index.html")
