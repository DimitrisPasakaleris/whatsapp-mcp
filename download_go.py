#!/usr/bin/env python3
"""Download and extract a portable Go installation (no admin required).

Usage:
    python download_go.py          # Downloads latest stable Go to ~/tools/go
    python download_go.py --check  # Just verify Go is available
"""

import argparse
import os
import platform
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

GO_VERSION = "1.26.3"
TOOLS_DIR = Path.home() / "tools"
GO_DIR = TOOLS_DIR / "go"
GO_BIN = GO_DIR / "bin" / "go.exe"


def is_windows() -> bool:
    return platform.system() == "Windows"


def go_already_installed() -> bool:
    """Check if portable Go exists and works."""
    if not GO_BIN.exists():
        return False
    try:
        result = os.popen(f'"{GO_BIN}" version').read().strip()
        return result.startswith("go version")
    except Exception:
        return False


def download_go():
    """Download and extract Go portable ZIP."""
    if not is_windows():
        print("ERROR: This script only supports Windows portable installs.")
        print("On macOS/Linux, install Go via your package manager.")
        sys.exit(1)

    if go_already_installed():
        print(f"Go is already installed: {GO_BIN}")
        os.system(f'"{GO_BIN}" version')
        return

    url = f"https://go.dev/dl/go{GO_VERSION}.windows-amd64.zip"
    zip_path = TOOLS_DIR / f"go{GO_VERSION}.windows-amd64.zip"

    print(f"Downloading Go {GO_VERSION}...")
    print(f"URL: {url}")
    print(f"Destination: {GO_DIR}")
    print()

    TOOLS_DIR.mkdir(parents=True, exist_ok=True)

    # Download
    print("Downloading... (this may take a minute)")
    urllib.request.urlretrieve(url, zip_path)
    print(f"Downloaded: {zip_path.stat().st_size / 1024 / 1024:.1f} MB")

    # Remove old install if exists
    if GO_DIR.exists():
        print("Removing old Go installation...")
        shutil.rmtree(GO_DIR)

    # Extract
    print("Extracting...")
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(TOOLS_DIR)

    # Clean up ZIP
    zip_path.unlink()

    # Verify
    if not GO_BIN.exists():
        print("ERROR: Extraction failed — go.exe not found.")
        sys.exit(1)

    print()
    print("Go installed successfully!")
    os.system(f'"{GO_BIN}" version')
    print()
    print(f"Location: {GO_DIR}")
    print("No admin rights required. No PATH changes needed.")
    print("The launcher scripts will use this Go automatically.")


def main():
    parser = argparse.ArgumentParser(description="Download portable Go (no admin)")
    parser.add_argument("--check", action="store_true", help="Just check if Go is available")
    args = parser.parse_args()

    if args.check:
        if go_already_installed():
            print(f"Go is ready: {GO_BIN}")
            os.system(f'"{GO_BIN}" version')
            sys.exit(0)
        else:
            print(f"Go not found at {GO_BIN}")
            print("Run: python download_go.py")
            sys.exit(1)

    download_go()


if __name__ == "__main__":
    main()
