import httpx
import pytest
import respx

from edinet_mcp import list_filings
from edinet_mcp.client import API_URL


@pytest.mark.asyncio
@respx.mock
async def test_filters_and_keeps_key_out_of_logs(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("EDINET_API_KEY", "fixture-subscription-key")
    caplog.set_level("INFO", logger="httpx")
    route = respx.get(API_URL).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "metadata": {"status": "200", "resultset": {"count": 2}},
                    "results": [
                        {"docID": "S1000001", "docTypeCode": "120", "filerName": "サンプル"},
                        {"docID": "S1000002", "docTypeCode": None, "filerName": None},
                    ],
                },
            ),
            httpx.Response(200, json={"metadata": {"status": "400"}}),
        ]
    )
    result = await list_filings("2026-06-30", filer="サンプル", document_type="120")
    assert route.calls[0].request.url.params["Subscription-Key"] == "fixture-subscription-key"
    assert result["total"] == 1
    assert result["items"][0]["document_id"] == "S1000001"
    with pytest.raises(ValueError, match="application status 400"):
        await list_filings("2026-06-30")
    assert "HTTP Request" in caplog.text
    assert "fixture-subscription-key" not in caplog.text
