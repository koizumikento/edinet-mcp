import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Annotated, Any, Literal

import httpx
from pydantic import Field, validate_call

DOCUMENTS_URL = "https://api.edinet-fsa.go.jp/api/v2/documents"
API_URL = f"{DOCUMENTS_URL}.json"
SOURCE_URL = "https://disclosure2.edinet-fsa.go.jp/"
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
Day = Annotated[str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")]
DocumentType = Annotated[str, Field(pattern=r"^[0-9]{3}$")]
Filer = Annotated[str, Field(min_length=1, max_length=100, pattern=r"\S")]
Limit = Annotated[int, Field(ge=1, le=100)]
Offset = Annotated[int, Field(ge=0)]
DocumentId = Annotated[str, Field(pattern=r"^[A-Z0-9]{8}$")]
DocumentFormat = Literal["pdf", "csv"]
DocumentSize = Annotated[int, Field(ge=1, le=MAX_DOCUMENT_BYTES)]


@dataclass(frozen=True)
class FilingDocument:
    document_id: str
    format: DocumentFormat
    filename: str
    media_type: str
    source_url: str
    content: bytes = field(repr=False)

    @property
    def metadata(self) -> dict[str, str | int]:
        return {
            "document_id": self.document_id,
            "format": self.format,
            "filename": self.filename,
            "media_type": self.media_type,
            "source_url": self.source_url,
            "size_bytes": len(self.content),
        }


class DocumentTooLargeError(ValueError):
    """An EDINET response exceeded the selected byte limit."""


def _redact_api_query(record: logging.LogRecord) -> bool:
    # HTTPX logs the URL at INFO, and EDINET requires the key in its query.
    args = record.args
    if isinstance(args, tuple) and len(args) == 5 and isinstance(url := args[1], httpx.URL):
        if url.host == "api.edinet-fsa.go.jp" and "Subscription-Key" in url.params:
            record.args = (args[0], url.copy_with(query=None), *args[2:])
    return True


logging.getLogger("httpx").addFilter(_redact_api_query)


def _api_key() -> str:
    key = os.environ.get("EDINET_API_KEY", "").strip()
    if not key:
        raise ValueError("Set EDINET_API_KEY to your registered EDINET key.")
    return key


@validate_call
async def list_filings(
    filing_date: Day,
    filer: Filer | None = None,
    document_type: DocumentType | None = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> dict[str, Any]:
    """List EDINET filing records for a date, filtered by filer or document type."""
    try:
        date.fromisoformat(filing_date)
    except ValueError:
        raise ValueError("Provide a valid filing date in YYYY-MM-DD format.") from None
    key = _api_key()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                API_URL, params={"date": filing_date, "type": 2, "Subscription-Key": key}
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"EDINET returned HTTP {exc.response.status_code}.") from None
    except httpx.RequestError:
        raise ValueError("Could not reach EDINET.") from None

    try:
        payload = response.json()
        status = int(payload["metadata"]["status"])
    except (ValueError, KeyError, TypeError):
        raise ValueError("EDINET returned an unexpected response.") from None
    if status != 200:
        raise ValueError(f"EDINET returned application status {status}.")
    try:
        rows = payload.get("results", [])
        if not isinstance(rows, list) or int(payload["metadata"]["resultset"]["count"]) != len(
            rows
        ):
            raise ValueError
        needle = filer.strip().casefold() if filer else ""
        matches = [
            row
            for row in rows
            if (document_type is None or row.get("docTypeCode") == document_type)
            and any(
                needle in (row.get(field) or "").casefold()
                for field in ("filerName", "edinetCode", "secCode")
            )
        ]
        items = [
            {
                "document_id": row["docID"],
                "filer": row.get("filerName"),
                "edinet_code": row.get("edinetCode"),
                "security_code": row.get("secCode"),
                "document_type": row.get("docTypeCode"),
                "description": row.get("docDescription"),
                "submitted_at": row.get("submitDateTime"),
                "withdrawal_status": row.get("withdrawalStatus"),
                "disclosure_status": row.get("disclosureStatus"),
                "pdf_flag": row.get("pdfFlag"),
                "csv_flag": row.get("csvFlag"),
            }
            for row in matches[offset : offset + limit]
        ]
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError("EDINET returned unexpected filing records.") from None
    return {
        "date": filing_date,
        "total": len(matches),
        "next_offset": offset + limit if offset + limit < len(matches) else None,
        "items": items,
        "source_url": SOURCE_URL,
    }


def _document_error(status: int) -> ValueError:
    hints = {
        400: "Check the document ID and requested format.",
        401: "Check EDINET_API_KEY.",
        403: "Check EDINET_API_KEY and whether the document is available.",
        404: "Check the document ID and the format flags from list_filings.",
        429: "Wait before requesting another filing.",
    }
    hint = hints.get(status, "Check EDINET availability.")
    return ValueError(f"EDINET returned status {status}. {hint}")


async def _read_limited(response: httpx.Response, max_bytes: int) -> bytes:
    body = bytearray()
    async for chunk in response.aiter_bytes(chunk_size=65536):
        if len(body) + len(chunk) > max_bytes:
            raise DocumentTooLargeError(f"EDINET response exceeds the {max_bytes}-byte limit.")
        body.extend(chunk)
    return bytes(body)


@validate_call
async def get_filing_document(
    document_id: DocumentId,
    format: DocumentFormat = "pdf",
    *,
    max_bytes: DocumentSize = MAX_DOCUMENT_BYTES,
) -> FilingDocument:
    """Retrieve a PDF or CSV ZIP from EDINET by the document ID returned by list_filings."""
    key = _api_key()
    url = f"{DOCUMENTS_URL}/{document_id}"
    type_code = 2 if format == "pdf" else 5
    media_type = "application/pdf" if format == "pdf" else "application/zip"
    accepted_types = {media_type}
    if format == "csv":
        accepted_types.add("application/octet-stream")

    try:
        async with (
            httpx.AsyncClient(timeout=20) as client,
            client.stream(
                "GET",
                url,
                params={"type": type_code, "Subscription-Key": key},
                headers={"Accept-Encoding": "identity"},
            ) as response,
        ):
            response.raise_for_status()
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                raise ValueError("EDINET returned an unexpected HTTP content encoding.")
            received_type = (
                response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            )
            if received_type == "application/json":
                try:
                    payload = json.loads(await _read_limited(response, 16 * 1024))
                    status = int(payload.get("StatusCode") or payload["metadata"]["status"])
                    if not 400 <= status <= 599:
                        raise ValueError
                except (ValueError, TypeError, KeyError, AttributeError):
                    raise ValueError(
                        "EDINET returned an unexpected document error response."
                    ) from None
                raise _document_error(status)
            if received_type not in accepted_types:
                raise ValueError("EDINET did not return the requested PDF or CSV ZIP.")
            content = await _read_limited(response, max_bytes)
    except httpx.HTTPStatusError as exc:
        raise _document_error(exc.response.status_code) from None
    except httpx.RequestError:
        raise ValueError("Could not reach EDINET.") from None

    signature = b"%PDF-" if format == "pdf" else b"PK\x03\x04"
    if not content.startswith(signature):
        raise ValueError("EDINET returned invalid bytes for the requested PDF or CSV ZIP.")
    suffix = ".pdf" if format == "pdf" else "-csv.zip"
    return FilingDocument(
        document_id,
        format,
        f"{document_id}{suffix}",
        media_type,
        f"{url}?type={type_code}",
        content,
    )
