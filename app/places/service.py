"""Find a named tourist point of interest near the listener."""

import os
from dataclasses import dataclass
from math import asin, cos, isfinite, radians, sin, sqrt
from pathlib import Path

import requests
from dotenv import dotenv_values

GEOAPIFY_URL = "https://api.geoapify.com/v2/places"
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
SEARCH_RADIUS_M = 500
PLACE_CATEGORIES = ["tourism.sights", "entertainment.museum"]


class PlaceLookupError(Exception):
    """Nearby place data is unavailable or malformed."""


@dataclass(frozen=True)
class NearbyPlace:
    name: str
    kind: str
    distance_m: int


def _distance_m(
    latitude: float, longitude: float, other_lat: float, other_lon: float
) -> int:
    """Calculate great-circle distance between two coordinates."""
    lat_delta = radians(other_lat - latitude)
    lon_delta = radians(other_lon - longitude)
    arc = (
        sin(lat_delta / 2) ** 2
        + cos(radians(latitude)) * cos(radians(other_lat)) * sin(lon_delta / 2) ** 2
    )
    return round(2 * 6_371_000 * asin(sqrt(arc)))


def find_nearby_place(latitude: float, longitude: float) -> NearbyPlace | None:
    """Return the nearest named sight or museum within 500 metres, if any."""
    api_key = os.getenv("GEOAPIFY_API_KEY") or dotenv_values(
        ENV_FILE, interpolate=False
    ).get("GEOAPIFY_API_KEY")
    if not api_key:
        raise PlaceLookupError("GEOAPIFY_API_KEY is not configured")

    location = {"lon": longitude, "lat": latitude}
    query = {
        "categories": PLACE_CATEGORIES,
        "filter": {"type": "circle", **location, "radius": SEARCH_RADIUS_M},
        "bias": {"type": "proximity", **location},
        "limit": 20,
    }
    try:
        response = requests.post(
            GEOAPIFY_URL,
            headers={"x-api-key": api_key},
            json=query,
            timeout=6,
        )
        response.raise_for_status()
        features = response.json()["features"]
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise PlaceLookupError("Could not look up nearby places") from exc
    if not isinstance(features, list):
        raise PlaceLookupError("Could not look up nearby places")

    nearest: NearbyPlace | None = None
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties, geometry = feature.get("properties"), feature.get("geometry")
        if not isinstance(properties, dict) or not isinstance(geometry, dict):
            continue
        name, categories = properties.get("name"), properties.get("categories")
        coordinates = geometry.get("coordinates")
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(categories, list) or not isinstance(coordinates, list):
            continue
        if len(coordinates) < 2:
            continue
        lon, lat = coordinates[:2]
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        if not isfinite(lat) or not isfinite(lon):
            continue
        distance = _distance_m(latitude, longitude, lat, lon)
        if distance > SEARCH_RADIUS_M:
            continue
        kind = (
            "museum"
            if any(
                isinstance(category, str)
                and category.startswith("entertainment.museum")
                for category in categories
            )
            else "sight"
        )
        place = NearbyPlace(
            name=" ".join(name.split())[:120],
            kind=kind,
            distance_m=distance,
        )
        if nearest is None or place.distance_m < nearest.distance_m:
            nearest = place
    return nearest
