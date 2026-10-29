"""Synthetic history catches cross-chat collisions and timestamp ties."""

import sqlite3

import pytest

from whatsapp_mcp import whatsapp


@pytest.fixture
def history(monkeypatch, tmp_path):
    path = tmp_path / "messages.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE chats (jid TEXT PRIMARY KEY, name TEXT, last_message_time TEXT);
            CREATE TABLE messages (id TEXT, chat_jid TEXT, sender TEXT, content TEXT,
                timestamp TEXT, is_from_me BOOL, media_type TEXT, PRIMARY KEY (id, chat_jid));
        """)
        for chat in ("a", "b"):
            conn.execute("INSERT INTO chats VALUES (?, ?, ?)", (chat, chat, "2024-01-01 12:00:02+00:00"))
        conn.executemany(
            "INSERT INTO messages VALUES (?, ?, 'fixture', ?, ?, 0, NULL)",
            [
                ("shared", "a", "older", "2024-01-01 12:00:01+00:00"),
                ("shared", "b", "newer", "2024-01-01 12:00:02+00:00"),
                ("tie", "b", "tied", "2024-01-01 12:00:02+00:00"),
            ],
        )
    monkeypatch.setattr(whatsapp, "MESSAGES_DB_PATH", str(path))
    monkeypatch.setattr(whatsapp, "get_sender_name", lambda value: value)
    return path


def test_context_keeps_colliding_ids_from_distinct_chats(history):
    messages = whatsapp.list_messages(limit=10, context_before=0, context_after=0)
    assert len(messages) == 3
    assert {(m["chat_jid"], m["id"]) for m in messages} == {("a", "shared"), ("b", "shared"), ("b", "tie")}


def test_context_preserves_requested_newest_order(history):
    with sqlite3.connect(history) as conn:
        conn.executemany(
            "INSERT INTO messages VALUES (?, 'a', 'fixture', ?, ?, 0, NULL)",
            [("previous", "context", "2024-01-01 12:00:03+00:00"), ("match", "needle", "2024-01-01 12:00:04+00:00")],
        )
    messages = whatsapp.list_messages(query="needle", limit=1, context_before=1, context_after=0, sort_by="newest")
    assert [m["id"] for m in messages] == ["match", "previous"]


def test_tied_last_messages_do_not_duplicate_chat_rows(history):
    chats = whatsapp.list_chats(limit=10)
    assert [chat["jid"] for chat in chats].count("b") == 1
    assert whatsapp.get_chat("b")["last_message"] == "tied"


def test_context_database_failure_is_structured(monkeypatch, tmp_path):
    bad = tmp_path / "broken.db"
    bad.write_bytes(b"not sqlite")
    monkeypatch.setattr(whatsapp, "MESSAGES_DB_PATH", str(bad))
    with pytest.raises(whatsapp.WhatsAppDBError):
        whatsapp.get_message_context("fixture")


def test_ambiguous_message_id_requires_chat(history):
    with pytest.raises(ValueError, match="multiple chats"):
        whatsapp.get_message_context("shared")
    assert whatsapp.get_message_context("shared", chat_jid="b").message.chat_jid == "b"


def test_context_includes_equal_timestamp_neighbors(history):
    context = whatsapp.get_message_context("shared", before=0, after=1, chat_jid="b")
    assert [message.id for message in context.after] == ["tie"]


@pytest.mark.parametrize("options", [{"limit": -1}, {"page": -1}, {"context_before": -1}, {"sort_by": "invalid"}])
def test_invalid_message_windows_are_rejected(history, options):
    with pytest.raises(ValueError):
        whatsapp.list_messages(**options)
