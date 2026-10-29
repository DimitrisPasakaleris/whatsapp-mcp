"""Bridge discovery uses the same configured paths and URL as data operations."""

import io
from unittest.mock import Mock
from urllib.error import HTTPError

from whatsapp_mcp import config as config_module
from whatsapp_mcp import server


def test_checkout_store_is_found_before_first_pair(monkeypatch, tmp_path):
    source = tmp_path / "src" / "whatsapp_mcp" / "config.py"
    bridge = tmp_path / "whatsapp-bridge"
    bridge.mkdir()
    monkeypatch.delenv("WHATSAPP_MCP_STORE_DIR", raising=False)
    monkeypatch.setattr(config_module, "__file__", str(source))
    assert config_module._default_store_dir() == bridge / "store"


def test_documented_database_overrides(monkeypatch, tmp_path):
    messages, sessions = tmp_path / "messages.db", tmp_path / "sessions.db"
    monkeypatch.setenv("WHATSAPP_DB_PATH", str(messages))
    monkeypatch.setenv("WHATSMEOW_DB_PATH", str(sessions))
    cfg = config_module.Config(config_dir=tmp_path, store_dir=tmp_path / "other")
    assert cfg.messages_db_path == messages
    assert cfg.whatsmeow_db_path == sessions


def test_api_override_controls_health_url(monkeypatch):
    monkeypatch.setenv("WHATSAPP_API_URL", "http://127.0.0.1:9191/custom/api/")
    opened = Mock()
    opened.return_value.__enter__ = Mock(return_value=Mock(status=200))
    opened.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(server.urllib.request, "urlopen", opened)
    assert server._is_bridge_running()
    assert opened.call_args.args[0] == "http://127.0.0.1:9191/custom/api/health"


def test_disconnected_bridge_is_still_running(monkeypatch):
    def disconnected(url, **kwargs):
        raise HTTPError(url, 503, "Disconnected", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(server.urllib.request, "urlopen", disconnected)
    assert server._is_bridge_running()


def test_autostart_checks_configured_port(monkeypatch):
    monkeypatch.setattr(server.config, "bridge_port", 9191)
    monkeypatch.setattr(server, "_is_bridge_running", lambda: False)
    ports = []
    monkeypatch.setattr(server, "_is_port_in_use", lambda port: ports.append(port) or True)
    started = Mock()
    monkeypatch.setattr(server, "_start_bridge", started)
    server._start_bridge_async()
    assert ports == [9191]
    started.assert_not_called()
