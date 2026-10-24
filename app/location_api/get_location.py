"""Estimate the backend server's location from its public IP address."""

import requests


def _lookup(url: str) -> dict[str, float | str]:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()
    if data.get("error") or data.get("success") is False:
        raise ValueError("IP location provider rejected the lookup")
    latitude, longitude = float(data["latitude"]), float(data["longitude"])
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("IP location provider returned invalid coordinates")
    return {
        "latitude": latitude,
        "longitude": longitude,
        "city": str(data.get("city", "")),
        "accuracy": "IP-based estimate",
    }


def get_my_location() -> dict[str, float | str]:
    """Return an IP estimate; fall back when the primary provider fails."""
    try:
        return _lookup("https://ipapi.co/json/")
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return _lookup("https://ipwho.is/")
