"""Centralized configuration for the WhatsApp MCP server.

Follows the same pattern as the Gmail MCP config:
- OS-appropriate config directories
- Dataclass-based configuration
- Sensible defaults that work out of the box
"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


def _default_config_dir() -> Path:
    """Return OS-appropriate config directory."""
    if env_dir := os.environ.get("WHATSAPP_MCP_CONFIG_DIR"):
        return Path(env_dir)

    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".config"

    return base / "whatsapp-mcp"


def _default_store_dir() -> Path:
    """Return the directory where the Go bridge stores its databases.

    By default this lives inside the project repo (whatsapp-bridge/store).
    If the repo layout changes, set WHATSAPP_MCP_STORE_DIR env var.
    """
    if env_dir := os.environ.get("WHATSAPP_MCP_STORE_DIR"):
        return Path(env_dir)

    # Try to find the bridge store relative to this file
    this_dir = Path(__file__).resolve().parent
    repo_store = this_dir.parent / "whatsapp-bridge" / "store"
    if repo_store.exists():
        return repo_store

    # Fallback: put it inside the config dir
    return _default_config_dir() / "store"


@dataclass
class Config:
    """Global configuration for the WhatsApp MCP server."""

    # Directories
    config_dir: Path = field(default_factory=_default_config_dir)
    store_dir: Path = field(default_factory=_default_store_dir)

    # Database paths
    @property
    def messages_db_path(self) -> Path:
        return self.store_dir / "messages.db"

    @property
    def whatsmeow_db_path(self) -> Path:
        return self.store_dir / "whatsapp.db"

    # Logging
    log_path: Path = field(default_factory=lambda: _default_config_dir() / "whatsapp-mcp.log")

    # Bridge REST API
    bridge_host: str = field(default_factory=lambda: os.getenv("WHATSAPP_BRIDGE_HOST", "127.0.0.1"))
    bridge_port: int = field(default_factory=lambda: int(os.getenv("WHATSAPP_BRIDGE_PORT", "8080")))

    @property
    def bridge_api_url(self) -> str:
        return f"http://{self.bridge_host}:{self.bridge_port}/api"

    # Webhook (only relevant if running the bridge yourself)
    webhook_url: str = field(
        default_factory=lambda: os.getenv("WEBHOOK_URL", "http://localhost:8769/whatsapp/webhook")
    )

    # Forward self-messages via webhook
    forward_self: bool = field(
        default_factory=lambda: os.getenv("FORWARD_SELF", "true").lower() in ("1", "true", "yes", "on")
    )

    def __post_init__(self):
        # Resolve to absolute paths and ensure directories exist
        self.config_dir = Path(self.config_dir).resolve()
        self.store_dir = Path(self.store_dir).resolve()
        self.log_path = Path(self.log_path).resolve()
        self.config_dir.mkdir(parents=True, exist_ok=True)


config = Config()
