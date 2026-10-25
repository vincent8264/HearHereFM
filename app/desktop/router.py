"""Loopback-only control surface used by desktop voice shortcuts."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.desktop.controller import DesktopBusyError, RadioController

router = APIRouter(prefix="/desktop", tags=["desktop"])


def local_controller(request: Request) -> RadioController:
    if request.client is None or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(403, "Desktop control is available only on this computer.")
    if request.headers.get("X-Radio-Activation") != "explicit":
        raise HTTPException(403, "An explicit desktop activation is required.")
    return request.app.state.radio_controller


Controller = Annotated[RadioController, Depends(local_controller)]


@router.get("/status")
def status(controller: Controller) -> dict:
    return {"service": "headless-radio-v1", **controller.status()}


@router.post("/activate", status_code=202)
def activate(controller: Controller) -> dict:
    """Only an explicit OS shortcut or local command can arm microphone capture."""
    try:
        return controller.activate()
    except DesktopBusyError as exc:
        raise HTTPException(503, str(exc), headers={"Retry-After": "1"}) from exc


class StartRequest(BaseModel):
    user_input: str | None = Field(default=None, min_length=1, max_length=2000)


@router.post("/start", status_code=202)
def start(controller: Controller, body: StartRequest | None = None) -> dict:
    """Start from context or an already transcribed string, without recording."""
    text = body.user_input if body is not None else None
    if text is not None and not text.strip():
        raise HTTPException(422, "Listening request cannot be blank.")
    try:
        return controller.start() if text is None else controller.activate(text)
    except DesktopBusyError as exc:
        raise HTTPException(503, str(exc), headers={"Retry-After": "1"}) from exc


@router.post("/stop", status_code=202)
def stop(controller: Controller) -> dict:
    return controller.stop()


@router.post("/shutdown", status_code=202)
def shutdown(request: Request, tasks: BackgroundTasks, controller: Controller) -> dict:
    callback = getattr(request.app.state, "request_shutdown", None)
    if callback is None:
        raise HTTPException(
            503, "Use the managed desktop launcher for server shutdown."
        )
    controller.stop()
    tasks.add_task(callback)
    return {"status": "shutting_down"}
