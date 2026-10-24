"""Serve a small browser client for device location and radio previews."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["location"])
CLIENT_DIR = Path(__file__).resolve().parent


@router.get("/location", include_in_schema=False)
def location_page() -> FileResponse:
    """Open the device-location client in the listener's browser."""
    return FileResponse(CLIENT_DIR / "client.html", media_type="text/html")


@router.get("/location/client.mjs", include_in_schema=False)
def location_script() -> FileResponse:
    """Serve the browser code from the same origin as the API."""
    return FileResponse(CLIENT_DIR / "client.mjs", media_type="text/javascript")
