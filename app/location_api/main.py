
from fastapi import APIRouter, HTTPException
import requests

from .get_location import get_my_location

router = APIRouter(prefix="/location", tags=["Location"])


@router.get("")
def fetch_location():
    try:
        return get_my_location()
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail="Failed to retrieve location from IP geolocation service",
        ) from e