# WhatsApp MCP Server — Setup Guide

A Model Context Protocol (MCP) server for WhatsApp, enabling Claude to read and send WhatsApp messages.

**No admin rights required.** Everything installs to your user folder.

---

## Quick Start (4 Steps, No Admin)

### 1. Install Prerequisites

| Tool | Download | Purpose |
|------|----------|---------|
| **Python 3.11+** | [python.org](https://python.org) | MCP server |
| **uv** | [astral.sh/uv](https://docs.astral.sh/uv/) | Python package manager |
| **Claude Desktop** | [claude.ai/download](https://claude.ai/download) | AI client |
| **FFmpeg** | [ffmpeg.org](https://ffmpeg.org/) | Optional — voice messages |

**Note:** You do **NOT** need admin rights for any of these. Install Python with "Add to PATH" checked. Install uv to your user folder.

### 2. Download Go (Portable, No Admin)

```bash
cd whatsapp-mcp
python download_go.py
```

This downloads Go to `C:\Users\<you>\tools\go` — no installer, no admin, no PATH changes. The launcher scripts find it automatically.

**Verify:**
```bash
python download_go.py --check
```

Expected output:
```
go version go1.26.3 windows/amd64
```

### 3. Start the WhatsApp Bridge

The bridge is a Go program that connects to WhatsApp's servers and stores messages locally.

**Option A — Double-click (easiest):**
```
launch.bat
```

**Option B — Command line:**
```bash
cd whatsapp-bridge
C:\Users\<you>\tools\go\bin\go.exe run .
```

On first run, a **QR code** appears in your terminal. Scan it with WhatsApp on your phone:

1. Open WhatsApp on your phone
2. Go to **Settings → Linked Devices → Link a Device**
3. Point your camera at the QR code in the terminal
4. Wait for "Successfully connected" in the terminal

**Your session is saved.** Next time you start the bridge, it connects automatically without scanning again.

Keep this terminal open. The bridge must stay running while you use WhatsApp via Claude.

### 4. Configure Claude Desktop

Add the MCP server to Claude Desktop's config:

**Both platforms** (after `pip install -e .` from the repo root):

```json
{
  "mcpServers": {
    "whatsapp": {
      "command": "whatsapp-mcp"
    }
  }
}
```

`whatsapp-mcp` is the console script registered by `pyproject.toml`. Edit:

- **Windows** — `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS** — `~/Library/Application Support/Claude/claude_desktop_config.json`

If you'd rather not install editable, run the module directly:

```json
{
  "mcpServers": {
    "whatsapp": {
      "command": "python",
      "args": ["-m", "whatsapp_mcp"],
      "cwd": "/path/to/whatsapp-mcp"
    }
  }
}
```

Save the file and **restart Claude Desktop**.

### 5. Start Using WhatsApp in Claude

Ask Claude things like:
- "Show my last 20 messages"
- "Send 'Hello' to +1234567890"
- "Find messages from last week"
- "Download the image from message XYZ"

---

## Configuration

All configuration lives in one place. The server automatically picks the right folder for your OS:

| OS | Config Directory |
|----|-----------------|
| Windows | `%APPDATA%\whatsapp-mcp` |
| macOS | `~/Library/Application Support/whatsapp-mcp` |
| Linux | `~/.config/whatsapp-mcp` |

### Config Files

| File | Purpose | Default Location |
|------|---------|-----------------|
| `whatsapp-mcp.log` | Server logs (rotates at 5MB) | Config dir |
| `messages.db` | Your message history | `whatsapp-bridge/store/` |
| `whatsapp.db` | WhatsApp session (QR auth) | `whatsapp-bridge/store/` |

### Environment Variables (Optional)

Set these **before** starting the bridge or MCP server if you need to customize:

| Variable | Default | Description |
|----------|---------|-------------|
| `WHATSAPP_BRIDGE_PORT` | `8080` | Port for Go bridge REST API |
| `WHATSAPP_BRIDGE_HOST` | `127.0.0.1` | Host for Go bridge REST API |
| `WEBHOOK_URL` | `http://localhost:8769/whatsapp/webhook` | Forward incoming messages here |
| `FORWARD_SELF` | `true` | Forward messages you send yourself |
| `WHATSAPP_MCP_CONFIG_DIR` | OS default | Override config directory |
| `WHATSAPP_MCP_STORE_DIR` | `whatsapp-bridge/store` | Override database directory |

---

## Updating

| You changed | What to do |
|------------|-----------|
| Bridge code (`whatsapp-bridge/*.go`) and run `go run .` | Nothing — `go run` recompiles each launch |
| Bridge code and you run a built binary | `go build -o whatsapp-bridge && ./whatsapp-bridge` |
| MCP server (`src/whatsapp_mcp/*.py`) | Restart Claude Desktop |

Updates **do not** require re-pairing or deleting databases. Your session and history are preserved.

---

## Troubleshooting

### "Go not found"
Run `python download_go.py` from the repo root. It installs Go to your user folder without admin rights.

### "Not connected to WhatsApp"
The bridge is not running or not connected. Check the bridge terminal for QR code or error messages.

### "Database is locked"
This should not happen with the optimizations applied. If it does, restart both the bridge and Claude Desktop.

### QR code not showing
Restart the bridge (`Ctrl+C`, then `go run .`). Check your terminal supports QR codes.

### No messages loading
Initial sync can take 5-30 minutes for large histories. Wait for "History sync complete" in the bridge logs.

### Windows: build errors
```bash
go env -w CGO_ENABLED=1
go run .
```

---

## Architecture

```
Claude Desktop ——MCP/stdio——▶ Python MCP Server ——HTTP——▶ Go Bridge ——WebSocket——▶ WhatsApp
                                      │                           │
                                      └──reads——▲                  └──stores——▲
                                         SQLite                      SQLite
                                      (messages.db)              (whatsapp.db)
```

- **Go Bridge**: Handles WhatsApp Web connection, QR auth, message storage, media download, webhook forwarding.
- **Python MCP Server**: Exposes tools to Claude, reads from SQLite, sends via REST API.
- **Local Storage**: All messages stay on your machine. Nothing is sent to Claude unless you ask.

---

## Security Notes

- Your WhatsApp session (`whatsapp.db`) is stored locally. Do not share it.
- Messages are stored in plaintext SQLite (`messages.db`). Encrypt your drive if needed.
- The bridge REST API binds to `127.0.0.1` only — not accessible from the network.
- Webhooks forward message content to external URLs. Only use trusted endpoints.
