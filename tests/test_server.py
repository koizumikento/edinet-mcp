import sys
from base64 import b64decode

import httpx
import pytest
import respx
from mcp import Client, StdioServerParameters
from mcp.types import BlobResourceContents, EmbeddedResource

from edinet_mcp import create_server
from edinet_mcp.client import DOCUMENTS_URL


@pytest.mark.asyncio
async def test_stdio_tool_contract() -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "edinet_mcp"])
    async with Client(params, mode="legacy", read_timeout_seconds=10) as client:
        result = await client.list_tools()
    assert {tool.name for tool in result.tools} == {"list_filings", "get_filing_document"}
    assert all(tool.annotations and tool.annotations.read_only_hint for tool in result.tools)


@pytest.mark.asyncio
@respx.mock
async def test_get_filing_document_embeds_original_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDINET_API_KEY", "fixture-subscription-key")
    url = f"{DOCUMENTS_URL}/S1000001"
    content = b"%PDF-1.7\nfixture-value"
    respx.get(url).mock(
        return_value=httpx.Response(
            200, headers={"Content-Type": "application/pdf"}, content=content
        )
    )
    async with Client(create_server()) as client:
        result = await client.call_tool("get_filing_document", {"document_id": "S1000001"})

    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["filename"] == "S1000001.pdf"
    assert isinstance(result.content[1], EmbeddedResource)
    resource = result.content[1].resource
    assert isinstance(resource, BlobResourceContents)
    assert resource.uri == f"{url}?type=2"
    assert resource.mime_type == "application/pdf"
    assert b64decode(resource.blob) == content


@pytest.mark.asyncio
@respx.mock
async def test_oversized_mcp_document_points_to_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDINET_API_KEY", "fixture-subscription-key")
    monkeypatch.setattr("edinet_mcp.server.MAX_EMBEDDED_BYTES", 7)
    respx.get(f"{DOCUMENTS_URL}/S1000001").mock(
        return_value=httpx.Response(
            200, headers={"Content-Type": "application/pdf"}, content=b"%PDF-1.7"
        )
    )
    async with Client(create_server()) as client:
        result = await client.call_tool("get_filing_document", {"document_id": "S1000001"})

    assert result.is_error
    assert "get-filing-document CLI" in str(result.content)
