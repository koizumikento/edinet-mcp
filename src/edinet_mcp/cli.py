import asyncio
import json
import sys
from argparse import SUPPRESS, ArgumentParser
from collections.abc import Sequence

import httpx

from .client import list_filings


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

    arguments = vars(parser.parse_args(argv))
    handler = arguments.pop("handler")
    try:
        result = asyncio.run(handler(**arguments))
    except (ValueError, OSError, httpx.HTTPError) as exc:
        parser.exit(1, f"{parser.prog}: {exc}\n")
    sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))
