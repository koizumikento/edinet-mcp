import asyncio
import json
import sys
from argparse import SUPPRESS, ArgumentParser
from collections.abc import Sequence
from pathlib import Path

import httpx

from .client import FilingDocument, get_filing_document, list_filings


def _write_document(path: Path, content: bytes) -> None:
    try:
        with path.open("xb") as stream:
            try:
                stream.write(content)
                stream.flush()
            except OSError:
                stream.close()
                path.unlink(missing_ok=True)
                raise
    except FileExistsError:
        raise ValueError("The output file already exists. Choose another --output path.") from None


def run_cli(argv: Sequence[str]) -> None:
    parser = ArgumentParser(prog="edinet-mcp")
    commands = parser.add_subparsers(required=True)

    command = commands.add_parser("list-filings", argument_default=SUPPRESS)
    command.add_argument("--date", dest="filing_date", required=True)
    command.add_argument("--filer")
    command.add_argument("--document-type")
    command.add_argument("--limit", type=int)
    command.add_argument("--offset", type=int)
    command.set_defaults(handler=list_filings)

    command = commands.add_parser("get-filing-document", argument_default=SUPPRESS)
    command.add_argument("--document-id", required=True)
    command.add_argument("--format", choices=("pdf", "csv"))
    command.add_argument("--output", type=Path, required=True)
    command.set_defaults(handler=get_filing_document)

    arguments = vars(parser.parse_args(argv))
    handler = arguments.pop("handler")
    output = arguments.pop("output", None)
    try:
        result = asyncio.run(handler(**arguments))
        if isinstance(result, FilingDocument) and output is not None:
            _write_document(output, result.content)
            result = {**result.metadata, "path": str(output)}
    except (ValueError, OSError, httpx.HTTPError) as exc:
        parser.exit(1, f"{parser.prog}: {exc}\n")
    sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))
