"""WhatsApp MCP server.

FastMCP server that wraps the Python-side tools defined in :mod:`whatsapp_mcp.whatsapp`,
auto-starts the Go bridge process if it isn't already running, and registers
13 tools for Claude (Desktop / Code).

Entry point: :func:`main`. Use the ``whatsapp-mcp`` console script (from
``pyproject.toml``) or ``python -m whatsapp_mcp``.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import config
from .whatsapp import (
    WhatsAppDBError,
    download_media as whatsapp_download_media,
    get_chat as whatsapp_get_chat,
    get_contact_chats as whatsapp_get_contact_chats,
    get_direct_chat_by_contact as whatsapp_get_direct_chat_by_contact,
    get_last_interaction as whatsapp_get_last_interaction,
    get_message_context as whatsapp_get_message_context,
    get_sender_name as whatsapp_get_sender_name,
    list_chats as whatsapp_list_chats,
    list_messages as whatsapp_list_messages,
    search_contacts as whatsapp_search_contacts,
    send_audio_message as whatsapp_audio_voice_message,
    send_file as whatsapp_send_file,
    send_message as whatsapp_send_message,
)


logger = logging.getLogger(__name__)


# Module-level FastMCP instance so the @mcp.tool() decorators below register
# at import time. main() configures logging and starts the bridge.
mcp = FastMCP("whatsapp")

_bridge_proc: subprocess.Popen | None = None
_bridge_start_lock = threading.Lock()


# ── Logging + startup banner ─────────────────────────────────────────────────

def _setup_logging() -> None:
    """Configure rotating file logging. Keeps stdout clean for MCP stdio transport."""
    config.config_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        handlers=[
            RotatingFileHandler(
                config.log_path, encoding="utf-8", maxBytes=5 * 1024 * 1024, backupCount=3
            ),
        ],
    )
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

    logger.info("WhatsApp MCP server starting")
    logger.info("Config directory: %s", config.config_dir)
    logger.info("Store directory:  %s", config.store_dir)
    logger.info("Messages DB:      %s", config.messages_db_path)
    logger.info("Whatsmeow DB:     %s", config.whatsmeow_db_path)
    logger.info("Log file:         %s", config.log_path)
    logger.info("Bridge API:       %s", config.bridge_api_url)
    logger.info("Webhook URL:      %s", config.webhook_url)


# ── Auto-start Go bridge if not running ──────────────────────────────────────

def _find_go() -> str | None:
    """Find the Go binary: prefer the portable install at ~/tools/go, fall back to PATH."""
    portable = Path.home() / "tools" / "go" / "bin" / "go.exe"
    if portable.exists():
        return str(portable)
    return shutil.which("go")


def _is_port_in_use(port: int = 8080) -> bool:
    """Check whether ``port`` on localhost is already bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _is_bridge_running() -> bool:
    try:
        url = config.bridge_api_url.replace("/api", "") + "/health"
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return False


def _bridge_dir() -> Path:
    """Locate ``whatsapp-bridge/`` relative to the installed package.

    src/whatsapp_mcp/server.py lives 3 levels below the repo root, so we walk
    up to the project root and append ``whatsapp-bridge/``.
    """
    return Path(__file__).resolve().parents[2] / "whatsapp-bridge"


def _start_bridge() -> subprocess.Popen | None:
    go_cmd = _find_go()
    if not go_cmd:
        logger.error("Go not found. Run: python download_go.py")
        return None

    bridge_dir = _bridge_dir()
    if not bridge_dir.exists():
        logger.error("Bridge directory not found: %s", bridge_dir)
        return None

    logger.info("Starting WhatsApp bridge at %s ...", bridge_dir)
    env = os.environ.copy()
    if "tools" in go_cmd and "go" in go_cmd:
        env["GOROOT"] = str(Path(go_cmd).parent.parent)
        env["PATH"] = str(Path(go_cmd).parent) + os.pathsep + env.get("PATH", "")

    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
        stdout_arg = None
        stderr_arg = None
    else:
        stdout_arg = subprocess.DEVNULL
        stderr_arg = subprocess.DEVNULL

    proc = subprocess.Popen(
        [go_cmd, "run", "."],
        cwd=str(bridge_dir),
        env=env,
        stdout=stdout_arg,
        stderr=stderr_arg,
        **kwargs,
    )

    for _ in range(30):
        if _is_bridge_running():
            logger.info("Bridge is online (PID %d)", proc.pid)
            return proc
        time.sleep(1)

    logger.warning("Bridge did not respond to health check yet. It may still be showing a QR code.")
    return proc


def _start_bridge_async() -> None:
    """Start the Go bridge in a background thread so MCP init isn't blocked."""
    global _bridge_proc
    with _bridge_start_lock:
        if _is_bridge_running() or _is_port_in_use(8080):
            logger.info("Bridge is already running (detected by health check or port bind).")
            return
        _bridge_proc = _start_bridge()


# ── Helper to wrap DB-backed tools so WhatsAppDBError surfaces cleanly ───────

def _db_error_response(operation: str, exc: WhatsAppDBError) -> dict[str, Any]:
    logger.error("WhatsAppDBError in %s: %s", operation, exc)
    return {"error": "database_error", "operation": operation, "message": str(exc)}


# ── Tools ────────────────────────────────────────────────────────────────────

@mcp.tool()
def search_contacts(query: str) -> list[dict[str, Any]] | dict[str, Any]:
    """Search WhatsApp contacts by name or phone number.

    Args:
        query: Search term to match against contact names or phone numbers
    """
    try:
        return whatsapp_search_contacts(query)
    except WhatsAppDBError as e:
        return _db_error_response("search_contacts", e)


@mcp.tool()
def get_contact(
    identifier: str | None = None,
    phone_number: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    """Look up a WhatsApp contact by phone number, LID, or full JID.

    Automatically detects the identifier type and queries appropriately.

    Args:
        identifier: Phone number, LID, or full JID. Examples:
                    - "12025551234" (phone number)
                    - "184125298348272" (LID - long numeric)
                    - "12025551234@s.whatsapp.net" (phone JID)
                    - "184125298348272@lid" (LID JID)
        phone_number: Backward-compatible alias for ``identifier``.
        phone: Backward-compatible alias for ``identifier`` (matches README parameter name).

    Returns:
        Dictionary with jid, name, display_name, is_lid, and resolved status
    """
    if identifier is None:
        identifier = phone_number
    if identifier is None:
        identifier = phone
    if identifier is None:
        raise ValueError("Missing required argument: identifier (or phone_number / phone)")

    identifier = identifier.strip()
    if not identifier:
        raise ValueError("identifier must be non-empty")

    if "@" in identifier:
        jid = identifier
        is_lid = jid.endswith("@lid") or jid.split("@", 1)[-1] == "lid"
    else:
        digits = "".join(c for c in identifier if c.isdigit())
        if digits:
            if len(digits) > 15:
                jid = f"{digits}@lid"
                is_lid = True
            else:
                jid = f"{digits}@s.whatsapp.net"
                is_lid = False
        else:
            jid = identifier
            is_lid = False

    jid_user = jid.split("@", 1)[0]

    display_name: str | None = None
    resolved = False

    candidates: list[tuple[str, bool]] = [(jid, is_lid)]
    if "@" not in identifier and identifier.isdigit() and len(identifier) == 15:
        candidates.append((f"{identifier}@lid", True))

    chat = None
    try:
        for candidate_jid, candidate_is_lid in candidates:
            chat = whatsapp_get_chat(candidate_jid, include_last_message=False)
            if chat:
                jid = candidate_jid
                is_lid = candidate_is_lid
                jid_user = jid.split("@", 1)[0]
                break

        if chat and chat.get("name"):
            display_name = chat["name"]
            resolved = display_name not in (jid, jid_user)
        else:
            display_name = whatsapp_get_sender_name(jid)
            resolved = display_name not in (jid, jid_user, identifier)
    except WhatsAppDBError as e:
        return _db_error_response("get_contact", e)

    return {
        "identifier": identifier,
        "jid": jid,
        "phone_number": jid_user if not is_lid else None,
        "lid": jid_user if is_lid else None,
        "name": display_name if resolved else jid_user,
        "display_name": display_name,
        "is_lid": is_lid,
        "resolved": resolved,
    }


@mcp.tool()
def list_messages(
    after: str | None = None,
    before: str | None = None,
    sender_phone_number: str | None = None,
    chat_jid: str | None = None,
    query: str | None = None,
    limit: int = 50,
    page: int = 0,
    include_context: bool = True,
    context_before: int = 1,
    context_after: int = 1,
    sort_by: str = "newest",
) -> list[dict[str, Any]] | dict[str, Any]:
    """Get WhatsApp messages matching specified criteria with optional context.

    Each message includes sender_display showing "Name (phone)" for easy identification.

    Args:
        after: ISO-8601 date string (e.g., "2026-01-01" or "2026-01-01T09:00:00")
        before: ISO-8601 date string (e.g., "2026-01-09" or "2026-01-09T18:00:00")
        sender_phone_number: Phone number to filter by sender (e.g., "12025551234")
        chat_jid: Chat JID to filter by (e.g., "12025551234@s.whatsapp.net" or group JID)
        query: Search term to filter messages by content
        limit: Max messages to return (default 50, max 500)
        page: Page number for pagination (default 0)
        include_context: Include surrounding messages for context (default True)
        context_before: Messages to include before each match (default 1)
        context_after: Messages to include after each match (default 1)
        sort_by: "newest" (default, most recent first) or "oldest" (chronological)
    """
    limit = min(limit, 500)
    try:
        return whatsapp_list_messages(
            after=after,
            before=before,
            sender_phone_number=sender_phone_number,
            chat_jid=chat_jid,
            query=query,
            limit=limit,
            page=page,
            include_context=include_context,
            context_before=context_before,
            context_after=context_after,
            sort_by=sort_by,
        )
    except WhatsAppDBError as e:
        return _db_error_response("list_messages", e)


@mcp.tool()
def list_chats(
    query: str | None = None,
    limit: int = 50,
    page: int = 0,
    include_last_message: bool = True,
    sort_by: str = "last_active",
) -> list[dict[str, Any]] | dict[str, Any]:
    """Get WhatsApp chats matching specified criteria.

    Args:
        query: Search term to filter chats by name or JID
        limit: Max chats to return (default 50, max 200)
        page: Page number for pagination (default 0)
        include_last_message: Include the last message in each chat (default True)
        sort_by: "last_active" (default, most recent first) or "name" (alphabetical)
    """
    limit = min(limit, 200)
    try:
        return whatsapp_list_chats(
            query=query,
            limit=limit,
            page=page,
            include_last_message=include_last_message,
            sort_by=sort_by,
        )
    except WhatsAppDBError as e:
        return _db_error_response("list_chats", e)


@mcp.tool()
def get_chat(chat_jid: str, include_last_message: bool = True) -> dict[str, Any]:
    """Get WhatsApp chat metadata by JID.

    Args:
        chat_jid: The JID of the chat to retrieve
        include_last_message: Whether to include the last message (default True)
    """
    try:
        return whatsapp_get_chat(chat_jid, include_last_message)
    except WhatsAppDBError as e:
        return _db_error_response("get_chat", e)


@mcp.tool()
def get_direct_chat_by_contact(sender_phone_number: str) -> dict[str, Any]:
    """Get WhatsApp chat metadata by sender phone number.

    Args:
        sender_phone_number: The phone number to search for
    """
    try:
        return whatsapp_get_direct_chat_by_contact(sender_phone_number)
    except WhatsAppDBError as e:
        return _db_error_response("get_direct_chat_by_contact", e)


@mcp.tool()
def get_contact_chats(jid: str, limit: int = 20, page: int = 0) -> list[dict[str, Any]] | dict[str, Any]:
    """Get all WhatsApp chats involving the contact.

    Args:
        jid: The contact's JID to search for
        limit: Maximum number of chats to return (default 20)
        page: Page number for pagination (default 0)
    """
    try:
        return whatsapp_get_contact_chats(jid, limit, page)
    except WhatsAppDBError as e:
        return _db_error_response("get_contact_chats", e)


@mcp.tool()
def get_last_interaction(jid: str) -> dict[str, Any]:
    """Get the most recent WhatsApp message involving the contact.

    Args:
        jid: The JID of the contact to search for

    Returns:
        Message dictionary with id, timestamp, sender, content, etc. or empty dict if not found.
    """
    try:
        message = whatsapp_get_last_interaction(jid)
    except WhatsAppDBError as e:
        return _db_error_response("get_last_interaction", e)
    return message if message else {}


@mcp.tool()
def get_message_context(message_id: str, before: int = 5, after: int = 5) -> dict[str, Any]:
    """Get context around a specific WhatsApp message.

    Args:
        message_id: The ID of the message to get context for
        before: Number of messages to include before the target message (default 5)
        after: Number of messages to include after the target message (default 5)
    """
    try:
        return whatsapp_get_message_context(message_id, before, after)
    except WhatsAppDBError as e:
        return _db_error_response("get_message_context", e)


@mcp.tool()
def send_message(recipient: str, message: str) -> dict[str, Any]:
    """Send a WhatsApp message to a person or group. For group chats use the JID.

    Args:
        recipient: The recipient — either a phone number with country code but no + or other symbols,
                 or a JID (e.g., "123456789@s.whatsapp.net" or a group JID like "123456789@g.us")
        message: The message text to send

    Returns:
        A dictionary containing success status and a status message
    """
    if not recipient:
        return {"success": False, "message": "Recipient must be provided"}
    success, status_message = whatsapp_send_message(recipient, message)
    return {"success": success, "message": status_message}


@mcp.tool()
def send_file(recipient: str, media_path: str) -> dict[str, Any]:
    """Send a file (image / raw audio / video / document) via WhatsApp. For group messages use the JID.

    Args:
        recipient: The recipient — either a phone number with country code but no + or other symbols,
                 or a JID (e.g., "123456789@s.whatsapp.net" or a group JID like "123456789@g.us")
        media_path: The absolute path to the media file to send (image, video, document)

    Returns:
        A dictionary containing success status and a status message
    """
    success, status_message = whatsapp_send_file(recipient, media_path)
    return {"success": success, "message": status_message}


@mcp.tool()
def send_audio_message(recipient: str, media_path: str) -> dict[str, Any]:
    """Send any audio file as a WhatsApp audio message. For group messages use the JID.

    If ffmpeg isn't installed, use ``send_file`` instead.

    Args:
        recipient: The recipient — either a phone number with country code but no + or other symbols,
                 or a JID (e.g., "123456789@s.whatsapp.net" or a group JID like "123456789@g.us")
        media_path: The absolute path to the audio file (will be converted to Opus .ogg if needed)

    Returns:
        A dictionary containing success status and a status message
    """
    success, status_message = whatsapp_audio_voice_message(recipient, media_path)
    return {"success": success, "message": status_message}


@mcp.tool()
def download_media(message_id: str, chat_jid: str) -> dict[str, Any]:
    """Download media from a WhatsApp message and get the local file path.

    Args:
        message_id: The ID of the message containing the media
        chat_jid: The JID of the chat containing the message

    Returns:
        A dictionary containing success status, a status message, and the file path if successful
    """
    file_path = whatsapp_download_media(message_id, chat_jid)
    if file_path:
        return {"success": True, "message": "Media downloaded successfully", "file_path": file_path}
    return {"success": False, "message": "Failed to download media"}


# ── Shutdown handling + entry point ──────────────────────────────────────────

def shutdown_handler(signum, frame) -> None:  # noqa: ARG001 — signal handler signature
    """Handle shutdown signals gracefully so the bridge process isn't orphaned."""
    global _bridge_proc
    if _bridge_proc is not None:
        logger.info("Stopping bridge (PID %d)...", _bridge_proc.pid)
        _bridge_proc.terminate()
        try:
            _bridge_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _bridge_proc.kill()
    sys.exit(0)


def main() -> None:
    """Console-script entry point: configure logging, spawn the bridge, run the MCP server."""
    _setup_logging()
    threading.Thread(target=_start_bridge_async, daemon=True).start()
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    logger.info("Server entering mcp.run()")
    try:
        mcp.run(transport="stdio")
    finally:
        shutdown_handler(None, None)


if __name__ == "__main__":
    main()
