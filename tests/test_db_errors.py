"""Regression tests for WhatsAppDBError: real DB failures must not silently return [] or None."""

from __future__ import annotations

import pytest

from whatsapp_mcp import whatsapp
from whatsapp_mcp.whatsapp import WhatsAppDBError


@pytest.fixture
def broken_db(monkeypatch, tmp_path):
    """Point MESSAGES_DB_PATH at a path that exists but is not a SQLite DB.

    Triggers ``sqlite3.DatabaseError`` (a subclass of sqlite3.Error) on the
    first query, which is the failure mode we want to verify surfaces as
    ``WhatsAppDBError`` instead of an empty result.
    """
    bad_path = tmp_path / "not-a-db.bin"
    bad_path.write_bytes(b"this is not a sqlite database, just bytes")
    monkeypatch.setattr(whatsapp, "MESSAGES_DB_PATH", str(bad_path))
    return bad_path


def test_list_messages_raises_on_bad_db(broken_db):
    with pytest.raises(WhatsAppDBError):
        whatsapp.list_messages(limit=10, include_context=False)


def test_list_chats_raises_on_bad_db(broken_db):
    with pytest.raises(WhatsAppDBError):
        whatsapp.list_chats(limit=10)


def test_get_contact_chats_raises_on_bad_db(broken_db):
    with pytest.raises(WhatsAppDBError):
        whatsapp.get_contact_chats("1234567890@s.whatsapp.net")


def test_get_last_interaction_raises_on_bad_db(broken_db):
    with pytest.raises(WhatsAppDBError):
        whatsapp.get_last_interaction("1234567890@s.whatsapp.net")


def test_get_chat_raises_on_bad_db(broken_db):
    with pytest.raises(WhatsAppDBError):
        whatsapp.get_chat("1234567890@s.whatsapp.net")


def test_get_direct_chat_by_contact_raises_on_bad_db(broken_db):
    with pytest.raises(WhatsAppDBError):
        whatsapp.get_direct_chat_by_contact("1234567890")
