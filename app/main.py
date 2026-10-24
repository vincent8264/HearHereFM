"""FastAPI application entry point."""

from fastapi import FastAPI

app = FastAPI(title="Hackathon Starter", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Report whether the application is running."""
    return {"status": "ok"}
