# location_tool.py
import requests

# Uses Ipapi which uses public IP address to give approximately location

def get_my_location():
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