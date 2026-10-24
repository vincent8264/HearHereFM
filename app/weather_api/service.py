import requests


def get_weather(latitude, longitude):
    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,precipitation,rain,showers",
        "temperature_unit": "fahrenheit",
        "precipitation_unit": "inch",
        "timezone": "auto",
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()
    current = data["current"]

    return {
        "time": current["time"],
        "temperature_f": current["temperature_2m"],
        "precipitation_in": current["precipitation"],
        "rain_in": current["rain"],
        "showers_in": current["showers"],
    }
