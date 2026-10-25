"""A bounded, cancellable background radio session with explicit microphone gating."""

import logging
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from threading import Event, RLock

from app.desktop.services import DesktopServices, PreparedSection
from app.radio.schemas import PlayedMusic, PlayedNarration, PlayedSection, RadioRequest

logger = logging.getLogger(__name__)


class DesktopBusyError(RuntimeError):
    """The controller is closing and cannot accept another command."""


class RadioController:
    def __init__(self, services: DesktopServices | None = None) -> None:
        self.services = services or DesktopServices()
        self._lock = RLock()
        self._session = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="radio-session"
        )
        self._preparation = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="radio-next"
        )
        self._cancel = Event()
        self._revision = 0
        self._capture_pending = False
        self._request_key: tuple[bool, str | None] | None = None
        self._phase = "idle"
        self._error: str | None = None
        self._history: list[PlayedSection] = []
        self._user_input: str | None = None
        self._closed = False

    def status(self) -> dict:
        with self._lock:
            return {
                "phase": self._phase,
                "microphone_open": self._phase == "listening",
                "error": self._error,
                "history": [entry.model_dump() for entry in self._history],
                "has_user_input": self._user_input is not None,
            }

    def activate(self, text: str | None = None) -> dict:
        return self._schedule(text, capture=text is None)

    def start(self) -> dict:
        """Start with contextual choices, clearing previous listener guidance."""
        return self._schedule(None, capture=False)

    def _schedule(self, text: str | None, *, capture: bool) -> dict:
        with self._lock:
            if self._closed:
                raise DesktopBusyError("Radio is shutting down.")
            key = (capture, text)
            if self._request_key == key and (
                self._capture_pending
                or (not capture and self._phase in {"activation_pending", "preparing"})
                or (key == (False, None) and self._phase in {"music", "narration"})
            ):
                return self.status()
            self._cancel.set()
            self._cancel = Event()
            self._revision += 1
            revision = self._revision
            self._capture_pending = True
            self._request_key = key
            self._phase = "activation_pending"
            self._error = None
            self._session.submit(self._activate, revision, self._cancel, text, capture)
            return self.status()

    def stop(self) -> dict:
        with self._lock:
            if self._closed or self._phase in {"idle", "stopping"}:
                return self.status()
            self._cancel.set()
            self._revision += 1
            self._capture_pending = False
            self._request_key = None
            self._error = None
            self._phase = "stopping"
            self._session.submit(self._settle_stop, self._revision)
            return self.status()

    def _settle_stop(self, revision: int) -> None:
        with self._lock:
            if revision != self._revision:
                return
        try:
            self.services.pause()
        except Exception:  # noqa: BLE001 -- Do not claim stopped playback when Spotify pause failed.
            with self._lock:
                if revision == self._revision:
                    self._error = (
                        "Could not confirm Spotify pause. Check the playback device."
                    )
                    self._phase = "error"
            return
        self._set_phase(revision, "idle")

    def _set_phase(self, revision: int, phase: str) -> None:
        with self._lock:
            if revision == self._revision:
                self._phase = phase

    def _activate(
        self, revision: int, cancel: Event, text: str | None, capture: bool
    ) -> None:
        try:
            if cancel.is_set():
                return
            self.services.pause()
            if capture:
                self._set_phase(revision, "prompting")
                if not self.services.prompt(cancel) or cancel.wait(0.3):
                    return
                self._set_phase(revision, "listening")
                text = self.services.capture(cancel)
            if cancel.is_set():
                return
            if text is not None and (not text.strip() or len(text) > 2000):
                raise ValueError("Spoken request must contain 1 to 2,000 characters.")
            if text is not None and text.strip().casefold().strip(".!。！") in {
                "cancel",
                "cancel radio",
                "never mind",
                "stop",
                "stop radio",
                "取消",
                "停止",
                "停止播放",
                "取消播放",
            }:
                self._set_phase(revision, "idle")
                return
            with self._lock:
                if revision != self._revision:
                    return
                self._user_input = text.strip() if text is not None else None
                self._capture_pending = False
            self.services.ensure_ready()
            self._run(revision, cancel)
        except Exception as exc:  # noqa: BLE001 -- A worker failure must become a visible terminal state.
            logger.warning("Radio request failed (%s).", type(exc).__name__)
            with self._lock:
                if revision == self._revision and not cancel.is_set():
                    self._error = (
                        str(exc)
                        if isinstance(exc, RuntimeError)
                        else "Radio could not complete this request."
                    )
                    self._phase = "error"
            if not cancel.is_set():
                try:
                    self.services.pause()
                    self.services.error_notice(cancel)
                except Exception:  # noqa: BLE001 -- Audio failure must not hide the original error.
                    logger.warning("Could not play the radio error notice.")
        finally:
            try:
                self.services.pause()
            except Exception:  # noqa: BLE001 -- Shutdown must complete even if Spotify is offline.
                with self._lock:
                    if revision == self._revision:
                        self._error = "Could not confirm Spotify pause. Check the playback device."
                        self._phase = "error"
            with self._lock:
                if revision == self._revision:
                    self._capture_pending = False

    def _prepare(
        self, history: list[PlayedSection], user_input: str | None
    ) -> PreparedSection:
        context = self.services.context()
        request = RadioRequest(
            **context,
            current_state=history[-1].mode if history else "idle",
            played_history=history,
            user_input=user_input,
        )
        return self.services.prepare(request)

    def _await(self, future: Future, cancel: Event) -> PreparedSection | None:
        while not cancel.is_set():
            try:
                return future.result(timeout=0.1)
            except TimeoutError:
                if future.done():
                    raise
                continue
        future.cancel()
        return None

    def _run(self, revision: int, cancel: Event) -> None:
        future: Future | None = None

        def prepare_next() -> None:
            nonlocal future
            with self._lock:
                history = list(self._history)
                text = self._user_input
            future = self._preparation.submit(self._prepare, history, text)

        def started(section: PreparedSection) -> None:
            with self._lock:
                if cancel.is_set() or revision != self._revision:
                    return
                action = section.action
                entry = (
                    PlayedMusic(
                        mode="music",
                        song_title=action.song_title,
                        artist=action.artist,
                        spotify_uri=section.uri,
                    )
                    if action.mode == "music"
                    else PlayedNarration(mode="narration", text=action.text)
                )
                self._history = [*self._history, entry][-10:]
            self._set_phase(revision, action.mode)
            prepare_next()

        prepare_next()
        try:
            while not cancel.is_set():
                self._set_phase(revision, "preparing")
                section = self._await(future, cancel)
                if section is None or cancel.is_set():
                    return
                if section.action.mode == "music":
                    if not self.services.start_music(section, cancel):
                        return
                    started(section)
                    if not self.services.wait_music(section, cancel):
                        return
                elif not self.services.play_narration(
                    section, cancel, lambda current=section: started(current)
                ):
                    return
        finally:
            if future is not None:
                future.cancel()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._cancel.set()
        self._session.shutdown(wait=True, cancel_futures=True)
        self._preparation.shutdown(wait=True, cancel_futures=True)
