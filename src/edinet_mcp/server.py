import json
from base64 import b64encode
from collections.abc import Awaitable, Callable
from functools import wraps

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import (
    BlobResourceContents,
    CallToolResult,
    EmbeddedResource,
    TextContent,
    ToolAnnotations,
)

from .client import DocumentFormat, DocumentId, DocumentTooLargeError, list_filings
from .client import get_filing_document as fetch_filing_document

MAX_EMBEDDED_BYTES = 2 * 1024 * 1024

READ_ONLY = ToolAnnotations(
    read_only_hint=True, idempotent_hint=True, destructive_hint=False, open_world_hint=True
)


def _tool_errors[**P, R](function: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    @wraps(function)
    async def invoke(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await function(*args, **kwargs)
        except (ValueError, OSError, httpx.HTTPError) as exc:
            raise ToolError(str(exc)) from None

    return invoke


def create_server() -> MCPServer:
    mcp = MCPServer("edinet-mcp")
    mcp.tool(annotations=READ_ONLY)(_tool_errors(list_filings))

    @mcp.tool(annotations=READ_ONLY)
    @_tool_errors
    async def get_filing_document(
        document_id: DocumentId, format: DocumentFormat = "pdf"
    ) -> CallToolResult:
        """Retrieve a filing's PDF or CSV ZIP by ID. Use the CLI for files over 2 MiB."""
        try:
            document = await fetch_filing_document(
                document_id, format, max_bytes=MAX_EMBEDDED_BYTES
            )
        except DocumentTooLargeError:
            raise ValueError(
                "The EDINET file exceeds the MCP limit of 2 MiB. "
                "Use the get-filing-document CLI command."
            ) from None
        metadata = document.metadata
        return CallToolResult(
            content=[
                TextContent(type="text", text=json.dumps(metadata)),
                EmbeddedResource(
                    resource=BlobResourceContents(
                        uri=document.source_url,
                        mime_type=document.media_type,
                        blob=b64encode(document.content).decode("ascii"),
                    )
                ),
            ],
            structured_content=metadata,
        )

    return mcp
