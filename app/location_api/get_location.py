"""Estimate the backend server's location from its public IP address."""

import requests


def get_my_location() -> dict[str, float | str]:
    """Return an IP estimate; this is not the listener's device location."""
    response = requests.get(
        "https://ipapi.co/json/",
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()

    return {
        "latitude": data["latitude"],
        "longitude": data["longitude"],
        "city": data["city"],
        "accuracy": "IP-based estimate",
    }
