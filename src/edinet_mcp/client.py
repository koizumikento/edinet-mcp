import logging
import os
from datetime import date
from typing import Annotated, Any

import httpx
from pydantic import Field, validate_call

API_URL = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
SOURCE_URL = "https://disclosure2.edinet-fsa.go.jp/"
Day = Annotated[str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")]
DocumentType = Annotated[str, Field(pattern=r"^[0-9]{3}$")]
Filer = Annotated[str, Field(min_length=1, max_length=100, pattern=r"\S")]
Limit = Annotated[int, Field(ge=1, le=100)]
Offset = Annotated[int, Field(ge=0)]


def _redact_api_query(record: logging.LogRecord) -> bool:
    # HTTPX logs the URL at INFO, and EDINET requires the key in its query.
    args = record.args
    if isinstance(args, tuple) and len(args) == 5 and isinstance(url := args[1], httpx.URL):
        base_url = url.copy_with(query=None)
        if base_url == httpx.URL(API_URL):
            record.args = (args[0], base_url, *args[2:])
    return True


logging.getLogger("httpx").addFilter(_redact_api_query)


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
    key = os.environ.get("EDINET_API_KEY", "").strip()
    if not key:
        raise ValueError("Set EDINET_API_KEY to your registered EDINET key.")
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
