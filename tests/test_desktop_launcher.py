"""Test the launcher without starting processes or opening browsers."""

from unittest.mock import Mock

import pytest
import requests

from app.desktop import __main__ as launcher


def test_status_does_not_open_microphone_or_activate(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setattr(launcher, "ensure_server", Mock())
    monkeypatch.setattr(
        launcher, "server_status", lambda: {"phase": "idle", "microphone_open": False}
    )
    post = Mock()
    monkeypatch.setattr(launcher.requests, "post", post)
    assert launcher.main(["status"]) == 0
    assert '"microphone_open": false' in capsys.readouterr().out
    post.assert_not_called()


@pytest.mark.parametrize("command", ["activate", "start"])
def test_voice_launcher_uses_explicit_activation_header(
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    monkeypatch.setattr(launcher, "ensure_server", Mock())
    response = Mock(status_code=202)
    response.json.return_value = {"phase": "activation_pending"}
    post = Mock(return_value=response)
    monkeypatch.setattr(launcher.requests, "post", post)
    assert launcher.main([command]) == 0
    assert post.call_args.args[0].endswith(f"/desktop/{command}")
    assert post.call_args.kwargs["json"] is None
    assert post.call_args.kwargs["headers"]["X-Radio-Activation"] == "explicit"


def test_managed_server_is_not_started_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        launcher, "server_status", lambda: {"service": "headless-radio-v1"}
    )
    spawn = Mock()
    monkeypatch.setattr(launcher.subprocess, "Popen", spawn)
    launcher.ensure_server()
    spawn.assert_not_called()


def test_existing_different_server_is_not_killed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock(status_code=404)
    monkeypatch.setattr(launcher.requests, "get", Mock(return_value=response))
    with pytest.raises(RuntimeError, match="older/different"):
        launcher.server_status()


def test_unavailable_server_is_reported_without_starting_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        launcher.requests, "get", Mock(side_effect=requests.ConnectionError())
    )
    assert launcher.server_status() is None


def test_shutdown_does_not_launch_a_new_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "server_status", lambda: None)
    start = Mock()
    monkeypatch.setattr(launcher, "ensure_server", start)
    assert launcher.main(["shutdown"]) == 0
    start.assert_not_called()


def test_failed_command_returns_nonzero_without_secret_details(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setattr(launcher, "ensure_server", Mock())
    monkeypatch.setattr(
        launcher.requests,
        "post",
        Mock(side_effect=requests.ConnectionError("internal details")),
    )
    assert launcher.main(["activate"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "internal details" not in captured.err
