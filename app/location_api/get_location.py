# location_tool.py
import requests
import datetime
from zoneinfo import ZoneInfo

# Uses Ipapi which uses public IP address to give approximately location

def get_my_location():
    response = requests.get(
        "https://ipapi.co/json/",
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()

    timezone = data["timezone"]
    now = datetime.now(ZoneInfo(timezone))

    return {
        "latitude": data["latitude"],
        "longitude": data["longitude"],
        "city": data["city"],
        "accuracy": "IP-based estimate",
        "time": now.strftime("%I:%M:%S %p"),
        "day": now.strftime("%A"),
    }