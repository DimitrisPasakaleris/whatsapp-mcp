"""Smoke tests for WhatsApp MCP.

Unit checks here run on every CI build. The single real-bridge round-trip at
the bottom is marked ``integration`` and only runs when ``WHATSAPP_TEST_REAL=1``.
"""
from __future__ import annotations

import os

import pytest

from whatsapp_mcp import __version__, audio, config as config_module, server, whatsapp


EXPECTED_TOOLS = (
    "search_contacts",
    "get_contact",
    "list_messages",
    "list_chats",
    "get_chat",
    "get_direct_chat_by_contact",
    "get_contact_chats",
    "get_last_interaction",
    "get_message_context",
    "send_message",
    "send_file",
    "send_audio_message",
    "download_media",
)


def test_package_version_is_set() -> None:
    assert __version__ and isinstance(__version__, str)


def test_config_paths_resolve() -> None:
    cfg = config_module.config
    assert cfg.config_dir.is_absolute()
    assert cfg.bridge_api_url.startswith("http://")


def test_audio_module_loads() -> None:
    assert hasattr(audio, "convert_to_opus_ogg_temp")


def test_whatsapp_db_error_exists() -> None:
    assert issubclass(whatsapp.WhatsAppDBError, RuntimeError)


@pytest.mark.parametrize("name", EXPECTED_TOOLS)
def test_tool_is_exported_on_server(name: str) -> None:
    assert hasattr(server, name), f"server.{name} missing"


def test_expected_tool_count() -> None:
    assert len(EXPECTED_TOOLS) == 13


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("WHATSAPP_TEST_REAL") != "1",
    reason="requires WHATSAPP_TEST_REAL=1 + a paired WhatsApp bridge",
)
def test_list_chats_round_trip() -> None:
    """Hit the live bridge. Requires a running Go bridge and a paired session."""
    chats = whatsapp.list_chats(limit=1)
    assert isinstance(chats, list)
