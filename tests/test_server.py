import sys

import pytest
from mcp import Client, StdioServerParameters


@pytest.mark.asyncio
async def test_stdio_tool_contract() -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "edinet_mcp"])
    async with Client(params, mode="legacy", read_timeout_seconds=10) as client:
        result = await client.list_tools()
    assert {tool.name for tool in result.tools} == {"list_filings"}
    assert all(tool.annotations and tool.annotations.read_only_hint for tool in result.tools)
