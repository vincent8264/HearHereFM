"""FastAPI application entry point."""

from fastapi import FastAPI

from app.radio.router import router as radio_router
from app.weather_api.main import router as weather_router
from app.location_api.main import router as location_router

app = FastAPI(title="Hackathon Starter", version="0.1.0")

app.include_router(radio_router)
app.include_router(weather_router)
app.include_router(location_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Report whether the application is running."""
    return {"status": "ok"}


