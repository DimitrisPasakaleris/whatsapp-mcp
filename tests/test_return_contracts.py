"""Public return contracts used by MCP schema generation and formatters."""

from whatsapp_mcp import server, whatsapp


def test_empty_formatted_history_is_text():
    assert whatsapp.format_messages_list([]) == "No messages to display."


def test_missing_chat_is_not_an_exception(monkeypatch):
    monkeypatch.setattr(server, "whatsapp_get_chat", lambda *args: None)
    assert server.get_chat("missing@s.whatsapp.net") is None


def test_context_tool_preserves_structured_context(monkeypatch):
    context = whatsapp.MessageContext(message=None, before=[], after=[])
    monkeypatch.setattr(server, "whatsapp_get_message_context", lambda *args: context)
    assert server.get_message_context("fixture") is context
