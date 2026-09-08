"""Minimal browser client for exercising the conversation API."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(include_in_schema=False)
PROJECT_ROOT = Path(__file__).parents[2]
LOCAL_REACT_DIST = PROJECT_ROOT.parent / "frontend" / "dist"
CONTAINER_REACT_DIST = PROJECT_ROOT / "frontend" / "dist"
REACT_DIST = LOCAL_REACT_DIST if LOCAL_REACT_DIST.exists() else CONTAINER_REACT_DIST
FRONTEND_DIRECTORY = REACT_DIST if (REACT_DIST / "index.html").exists() else PROJECT_ROOT / "src" / "resources"
INDEX_FILE = FRONTEND_DIRECTORY / "index.html"


@router.get("/", response_class=FileResponse)
async def frontend() -> FileResponse:
    """Return the same-origin test client without embedding any credentials."""

    return FileResponse(INDEX_FILE, media_type="text/html")
