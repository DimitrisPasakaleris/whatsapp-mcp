"""Exercise real MCP stdio initialization/teardown without starting WhatsApp."""

import os
import sys

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_stdio_initialization_and_clean_teardown(tmp_path):
    # Disable bridge startup before main runs. No tool is invoked, no account
    # is opened, and all configuration stays in a synthetic temporary folder.
    code = (
        "from whatsapp_mcp import server; "
        "server._start_bridge_async = lambda: None; "
        "server._setup_logging = lambda: None; "
        "server.main()"
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", code],
        env={**os.environ, "WHATSAPP_MCP_CONFIG_DIR": str(tmp_path)},
    )
    with anyio.fail_after(20):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert {"list_chats", "send_message", "download_media"} <= {tool.name for tool in tools.tools}
