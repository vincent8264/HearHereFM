"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from app.radio.router import router as radio_router
from app.tts.jobs import SpeechJobs
from app.tts.router import router as tts_router
from app.weather_api.main import router as weather_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.speech_jobs = SpeechJobs()
    try:
        yield
    finally:
        await run_in_threadpool(app.state.speech_jobs.close)


app = FastAPI(title="Hackathon Starter", version="0.1.0", lifespan=lifespan)
app.include_router(radio_router)
app.include_router(tts_router)
app.include_router(weather_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Report whether the application is running."""
    return {"status": "ok"}
