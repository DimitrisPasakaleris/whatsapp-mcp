"""Launcher process ownership is tested with mocks, never a real bridge."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock, call

import pytest


@pytest.fixture
def launcher():
    spec = importlib.util.spec_from_file_location("launch_fixture", Path(__file__).resolve().parents[1] / "launch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bridge_only_waits_for_owned_process(monkeypatch, launcher):
    process = Mock()
    process.poll.return_value = 0
    monkeypatch.setattr(launcher.sys, "argv", ["launch.py", "--bridge-only"])
    monkeypatch.setattr(launcher, "is_bridge_running", lambda: False)
    monkeypatch.setattr(launcher, "start_bridge", lambda _: process)
    launcher.main()
    assert call() in process.wait.call_args_list
    process.terminate.assert_not_called()


def test_launcher_propagates_mcp_exit_status(monkeypatch, launcher):
    monkeypatch.setattr(launcher.sys, "argv", ["launch.py", "--mcp-only"])
    monkeypatch.setattr(launcher, "start_mcp_server", lambda _: 7)
    with pytest.raises(SystemExit) as error:
        launcher.main()
    assert error.value.code == 7


def test_mcp_subprocess_returns_failure(monkeypatch, launcher):
    monkeypatch.setattr(launcher.os, "chdir", lambda _: None)
    monkeypatch.setattr(launcher.shutil, "which", lambda _: None)
    monkeypatch.setattr(launcher.subprocess, "run", Mock(return_value=Mock(returncode=9)))
    assert launcher.start_mcp_server(Mock()) == 9
