from io import BytesIO
from zipfile import ZipFile

import httpx
import pytest
import respx

from edinet_mcp import get_filing_document, list_filings
from edinet_mcp.client import API_URL, DOCUMENTS_URL, DocumentFormat, DocumentTooLargeError

DOCUMENT_URL = f"{DOCUMENTS_URL}/S1000001"


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
                        {
                            "docID": "S1000001",
                            "docTypeCode": "120",
                            "filerName": "サンプル",
                            "pdfFlag": "1",
                            "csvFlag": "0",
                        },
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
    assert result["items"][0]["pdf_flag"] == "1"
    assert result["items"][0]["csv_flag"] == "0"
    with pytest.raises(ValueError, match="application status 400"):
        await list_filings("2026-06-30")
    assert "HTTP Request" in caplog.text
    assert "fixture-subscription-key" not in caplog.text


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    ("format", "type_code", "content_type", "media_type", "filename"),
    [
        ("pdf", "2", "application/pdf", "application/pdf", "S1000001.pdf"),
        ("csv", "5", "application/octet-stream", "application/zip", "S1000001-csv.zip"),
    ],
)
async def test_retrieves_original_document_bytes(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    format: DocumentFormat,
    type_code: str,
    content_type: str,
    media_type: str,
    filename: str,
) -> None:
    monkeypatch.setenv("EDINET_API_KEY", "fixture-subscription-key")
    caplog.set_level("INFO", logger="httpx")
    archive = BytesIO()
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("../fixture.csv", "column\nfixture-value\n")
    content = b"%PDF-1.7\nfixture-value" if format == "pdf" else archive.getvalue()
    route = respx.get(DOCUMENT_URL).mock(
        return_value=httpx.Response(200, headers={"Content-Type": content_type}, content=content)
    )

    document = await get_filing_document("S1000001", format)

    request = route.calls.last.request
    assert request.url.params["type"] == type_code
    assert request.url.params["Subscription-Key"] == "fixture-subscription-key"
    assert request.headers["Accept-Encoding"] == "identity"
    assert document.content == content
    assert document.metadata == {
        "document_id": "S1000001",
        "format": format,
        "filename": filename,
        "media_type": media_type,
        "source_url": f"{DOCUMENT_URL}?type={type_code}",
        "size_bytes": len(content),
    }
    assert "fixture-subscription-key" not in caplog.text
    assert "fixture-value" not in caplog.text


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    ("payload", "hint"),
    [
        ({"metadata": {"status": "404", "message": "untrusted-body"}}, "format flags"),
        ({"StatusCode": 401, "message": "untrusted-body"}, "Check EDINET_API_KEY"),
    ],
)
async def test_handles_document_json_errors_with_http_200(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object], hint: str
) -> None:
    monkeypatch.setenv("EDINET_API_KEY", "fixture-subscription-key")
    respx.get(DOCUMENT_URL).mock(return_value=httpx.Response(200, json=payload))
    with pytest.raises(ValueError, match=hint) as error:
        await get_filing_document("S1000001")
    assert "untrusted-body" not in str(error.value)
    assert "fixture-subscription-key" not in str(error.value)


@pytest.mark.asyncio
@respx.mock
async def test_limits_and_validates_document_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDINET_API_KEY", "fixture-subscription-key")
    respx.get(DOCUMENT_URL).mock(
        side_effect=[
            httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=b"%PDF-1.7"),
            httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"<html>"),
            httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=b"<html>"),
        ]
    )
    with pytest.raises(DocumentTooLargeError, match="7-byte limit"):
        await get_filing_document("S1000001", max_bytes=7)
    with pytest.raises(ValueError, match="did not return the requested"):
        await get_filing_document("S1000001")
    with pytest.raises(ValueError, match="invalid bytes"):
        await get_filing_document("S1000001")
