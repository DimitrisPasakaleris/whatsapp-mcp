#!/usr/bin/env python3
"""Launcher script for the WhatsApp MCP server.

Starts the Go bridge (if not already running) and then the Python MCP server.
Works without admin rights — uses portable Go from ~/tools/go if available.

Usage:
    python launch.py                 # Start bridge + MCP server
    python launch.py --bridge-only   # Start only the bridge
    python launch.py --mcp-only      # Start only the MCP server (bridge must be running)
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# Repo root + bridge directory. The Python package lives under src/whatsapp_mcp/
# but is launched via the console script registered in pyproject.toml.
SCRIPT_DIR = Path(__file__).resolve().parent
BRIDGE_DIR = SCRIPT_DIR / "whatsapp-bridge"

# Portable Go location (no admin install)
PORTABLE_GO = Path.home() / "tools" / "go" / "bin" / "go.exe"

# Default bridge URL
BRIDGE_HEALTH_URL = "http://127.0.0.1:8080/api/health"
BRIDGE_START_TIMEOUT = 30  # seconds


def _find_go() -> str | None:
    """Find Go binary: prefer portable install, then PATH."""
    if PORTABLE_GO.exists():
        return str(PORTABLE_GO)
    # Try PATH
    go_path = shutil.which("go")
    if go_path:
        return go_path
    return None


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
    )
    return logging.getLogger("launcher")


def is_bridge_running() -> bool:
    """Check if the Go bridge health endpoint is responding."""
    try:
        with urllib.request.urlopen(BRIDGE_HEALTH_URL, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_bridge(logger: logging.Logger) -> subprocess.Popen:
    """Start the Go bridge in the background."""
    if not BRIDGE_DIR.exists():
        logger.error("Bridge directory not found: %s", BRIDGE_DIR)
        logger.error("Make sure you are running from the repo root.")
        sys.exit(1)

    go_cmd = _find_go()
    if not go_cmd:
        logger.error("Go not found.")
        logger.error("Run: python download_go.py")
        logger.error("Or install Go from: https://go.dev/dl/")
        sys.exit(1)

    logger.info("Go found: %s", go_cmd)
    # Verify it works
    try:
        result = subprocess.run([go_cmd, "version"], capture_output=True, text=True, check=True)
        logger.info("Go version: %s", result.stdout.strip())
    except subprocess.CalledProcessError:
        logger.error("Go binary exists but failed to run: %s", go_cmd)
        sys.exit(1)

    logger.info("Starting WhatsApp bridge from %s...", BRIDGE_DIR)

    # Set GOROOT for portable install
    env = os.environ.copy()
    if str(PORTABLE_GO) in go_cmd:
        env["GOROOT"] = str(Path(go_cmd).parent.parent)
        env["PATH"] = str(Path(go_cmd).parent) + os.pathsep + env.get("PATH", "")

    # On Windows, use creationflags to avoid console window flash
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE

    proc = subprocess.Popen(
        [go_cmd, "run", "."],
        cwd=str(BRIDGE_DIR),
        env=env,
        **kwargs,
    )

    # Wait for bridge to come online
    logger.info("Waiting for bridge to start (timeout: %ds)...", BRIDGE_START_TIMEOUT)
    start = time.time()
    while time.time() - start < BRIDGE_START_TIMEOUT:
        if is_bridge_running():
            logger.info("Bridge is online!")
            return proc
        time.sleep(1)

    logger.warning("Bridge did not respond to health check within %d seconds.", BRIDGE_START_TIMEOUT)
    logger.warning("It may still be starting (e.g., showing QR code). Check the bridge window.")
    return proc


def start_mcp_server(logger: logging.Logger):
    """Start the Python MCP server via the installed console script.

    Falls back to ``python -m whatsapp_mcp`` if the console script isn't on PATH.
    Both routes resolve to :func:`whatsapp_mcp.server.main`.
    """
    logger.info("Starting WhatsApp MCP server (package: whatsapp_mcp)...")

    cmd: list[str]
    console_script = shutil.which("whatsapp-mcp")
    if console_script:
        cmd = [console_script]
    else:
        logger.info("Console script `whatsapp-mcp` not found; falling back to `python -m whatsapp_mcp`.")
        logger.info("Install with `pip install -e .` from the repo root for the faster path.")
        cmd = [sys.executable, "-m", "whatsapp_mcp"]

    # Ensure the working directory is the repo root so the server can locate
    # whatsapp-bridge/ via its relative path resolution.
    os.chdir(str(SCRIPT_DIR))
    logger.info("Server entering mcp.run() via %s", " ".join(cmd))
    subprocess.run(cmd)


def main():
    parser = argparse.ArgumentParser(description="Launch WhatsApp MCP")
    parser.add_argument("--bridge-only", action="store_true", help="Start only the bridge")
    parser.add_argument("--mcp-only", action="store_true", help="Start only the MCP server")
    args = parser.parse_args()

    logger = setup_logging()
    logger.info("=" * 50)
    logger.info("WhatsApp MCP Launcher")
    logger.info("=" * 50)

    bridge_proc = None

    try:
        if not args.mcp_only:
            if is_bridge_running():
                logger.info("Bridge is already running.")
            else:
                bridge_proc = start_bridge(logger)

        if not args.bridge_only:
            # Give bridge a moment to fully initialize if we just started it
            if bridge_proc and not is_bridge_running():
                logger.info("Waiting a few more seconds for bridge initialization...")
                for _ in range(5):
                    if is_bridge_running():
                        break
                    time.sleep(1)

            start_mcp_server(logger)

    except KeyboardInterrupt:
        logger.info("\nShutting down...")
    finally:
        if bridge_proc is not None:
            logger.info("Stopping bridge (PID %d)...", bridge_proc.pid)
            bridge_proc.terminate()
            try:
                bridge_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                bridge_proc.kill()


if __name__ == "__main__":
    main()
