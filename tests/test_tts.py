"""Exercise the TTS HTTP contract and WAV storage without model downloads."""

from pathlib import Path
from threading import Event
from time import monotonic, sleep
from unittest.mock import Mock

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.main import app
from app.radio import llm
from app.radio import service as radio_service
from app.tts.jobs import QueueFullError, SpeechJobs
from app.tts.service import TTSService, get_tts_service


@pytest.fixture
def service(tmp_path: Path) -> TTSService:
    service = TTSService(tmp_path)
    engine = Mock()
    engine.create.return_value = (np.zeros(2400, dtype=np.float32), 24000)
    service._engine = engine
    return service


@pytest.fixture
def client(service: TTSService):
    app.dependency_overrides[get_tts_service] = lambda: service
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_tts_service, None)


def test_synthesis_returns_playable_wav(
    client: TestClient, service: TTSService
) -> None:
    response = client.post("/tts", json={"text": " Welcome to San Diego. "})
    assert response.status_code == 200
    audio_url = response.json()["audio_url"]
    assert audio_url.startswith("http://testserver/tts/audio/")
    audio = client.get(audio_url)
    assert audio.status_code == 200
    assert audio.headers["content-type"] == "audio/wav"
    assert audio.content[:4] == b"RIFF"
    service._engine.create.assert_called_once_with(
        "Welcome to San Diego.", voice="af_sarah", speed=1.0, lang="en-us"
    )
    info = sf.info(next(service.audio_dir.glob("*.wav")))
    assert info.samplerate == 24000
    assert info.frames == 2400


@pytest.mark.parametrize("text", ["", " \n\t", "x" * 2001, None, 42])
def test_invalid_text_rejected(client: TestClient, text: object) -> None:
    assert client.post("/tts", json={"text": text}).status_code == 422


def test_missing_models_returns_503(client: TestClient, service: TTSService) -> None:
    service._engine = None
    response = client.post("/tts", json={"text": "Hello."})
    assert response.status_code == 503
    assert "download_tts_models.py" in response.json()["detail"]


def test_failed_inference_does_not_publish_audio(
    client: TestClient, service: TTSService
) -> None:
    service._engine.create.side_effect = RuntimeError("internal details")
    response = client.post("/tts", json={"text": "Hello."})
    assert response.status_code == 500
    assert response.json() == {"detail": "Could not generate speech."}
    assert list(service.audio_dir.glob("*")) == []


def test_empty_audio_is_not_published(client: TestClient, service: TTSService) -> None:
    service._engine.create.return_value = (np.array([]), 24000)
    assert client.post("/tts", json={"text": "Hello."}).status_code == 500
    assert list(service.audio_dir.glob("*")) == []


@pytest.mark.parametrize("filename", ["a" * 32 + ".wav", "model.onnx", "..%2Fsecret"])
def test_missing_or_invalid_audio_returns_404(
    client: TestClient, filename: str
) -> None:
    assert client.get(f"/tts/audio/{filename}").status_code == 404


def wait_for_job(jobs: SpeechJobs, job_id: str):
    deadline = monotonic() + 3
    while monotonic() < deadline:
        job = jobs.get(job_id)
        if job is not None and job.status in {"ready", "failed"}:
            return job
        sleep(0.01)
    pytest.fail("Background TTS did not finish.")


def test_background_submission_does_not_wait_for_synthesis(
    client: TestClient, service: TTSService
) -> None:
    started, release = Event(), Event()

    def generate(*args, **kwargs):
        started.set()
        if not release.wait(timeout=3):
            raise TimeoutError("Test did not release the synthesis worker.")
        return np.zeros(2400, dtype=np.float32), 24000

    service._engine.create.side_effect = generate
    try:
        response = client.post("/tts/jobs", json={"text": "Hello San Diego."})
        assert response.status_code == 202
        assert started.wait(timeout=1)
        body = response.json()
        assert body["status"] == "queued"
        assert body["audio_url"] is None
        running = client.get(body["status_url"]).json()
        assert running["status"] == "running"
        assert running["audio_url"] is None
        assert client.get("/health").status_code == 200
    finally:
        release.set()

    wait_for_job(app.state.speech_jobs, body["job_id"])
    ready = client.get(body["status_url"]).json()
    assert ready["status"] == "ready"
    assert ready["error"] is None
    assert client.get(ready["audio_url"]).content[:4] == b"RIFF"


def test_background_failure_is_reported(
    client: TestClient, service: TTSService
) -> None:
    service._engine = None
    response = client.post("/tts/jobs", json={"text": "Hello."})
    assert response.status_code == 202
    wait_for_job(app.state.speech_jobs, response.json()["job_id"])
    failed = client.get(response.json()["status_url"]).json()
    assert failed["status"] == "failed"
    assert failed["audio_url"] is None
    assert "download_tts_models.py" in failed["error"]


def test_unknown_job_returns_404(client: TestClient) -> None:
    assert client.get("/tts/jobs/unknown").status_code == 404


def test_queue_limit_returns_retryable_429(
    client: TestClient, service: TTSService
) -> None:
    release = Event()

    def generate(*args, **kwargs):
        if not release.wait(timeout=3):
            raise TimeoutError("Test did not release the synthesis worker.")
        return np.zeros(2400, dtype=np.float32), 24000

    service._engine.create.side_effect = generate
    try:
        for _ in range(8):
            assert client.post("/tts/jobs", json={"text": "Hello."}).status_code == 202
        response = client.post("/tts/jobs", json={"text": "Hello."})
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "5"
    finally:
        release.set()


def test_job_records_are_bounded_and_finished_records_are_evicted() -> None:
    jobs = SpeechJobs(max_records=1)
    try:
        first = jobs.submit("Hello.", lambda text: "first.wav")
        wait_for_job(jobs, first.job_id)
        second = jobs.submit("Hello again.", lambda text: "second.wav")
        wait_for_job(jobs, second.job_id)
        assert jobs.get(first.job_id) is None
        assert jobs.get(second.job_id).filename == "second.wav"
    finally:
        jobs.close()


def test_closed_worker_rejects_new_jobs() -> None:
    jobs = SpeechJobs()
    jobs.close()
    with pytest.raises(QueueFullError, match="shutting down"):
        jobs.submit("Hello.", lambda text: "unused.wav")


def test_unexpected_failure_is_terminal_and_does_not_stop_worker() -> None:
    jobs = SpeechJobs()

    def broken(text: str) -> str:
        raise ValueError("Sensitive input must not be exposed.")

    try:
        failed = jobs.submit("Hello.", broken)
        result = wait_for_job(jobs, failed.job_id)
        assert result.status == "failed"
        assert result.error == "Could not generate speech."
        next_job = jobs.submit("Next.", lambda text: "next.wav")
        assert wait_for_job(jobs, next_job.job_id).status == "ready"
    finally:
        jobs.close()


def test_radio_narration_can_be_pre_generated_and_downloaded(
    client: TestClient, service: TTSService, monkeypatch: pytest.MonkeyPatch
) -> None:
    narration = "A warm breeze follows the sunshine. Enjoy the ocean view."
    monkeypatch.setattr(radio_service, "find_nearby_place", lambda *_args: None)
    monkeypatch.setattr(
        llm, "_generate", lambda *_args: llm.NarrationResult(text=narration)
    )
    response = client.post(
        "/radio/next",
        json={
            "latitude": 32.7157,
            "longitude": -117.1611,
            "weather": "Sunny, 20 C",
            "time": "18:30",
            "current_state": "music",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"mode": "narration", "text": narration}
    queued = client.post("/tts/jobs", json={"text": response.json()["text"]})
    assert queued.status_code == 202
    wait_for_job(app.state.speech_jobs, queued.json()["job_id"])
    ready = client.get(queued.json()["status_url"]).json()
    assert ready["status"] == "ready"
    audio = client.get(ready["audio_url"])
    assert audio.status_code == 200
    assert audio.content[:4] == b"RIFF"
    service._engine.create.assert_called_once_with(
        narration, voice="af_sarah", speed=1.0, lang="en-us"
    )
