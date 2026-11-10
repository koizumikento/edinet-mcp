from pathlib import Path

import httpx
import pytest
import respx

from edinet_mcp.cli import run_cli
from edinet_mcp.client import DOCUMENTS_URL


@respx.mock
def test_download_writes_new_file_without_overwriting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EDINET_API_KEY", "fixture-subscription-key")
    content = b"%PDF-1.7\nfixture-value"
    respx.get(f"{DOCUMENTS_URL}/S1000001").mock(
        return_value=httpx.Response(
            200, headers={"Content-Type": "application/pdf"}, content=content
        )
    )
    path = tmp_path / "filing.pdf"
    argv = ["get-filing-document", "--document-id", "S1000001", "--output", str(path)]
    run_cli(argv)
    assert path.read_bytes() == content
    assert "fixture-subscription-key" not in capsys.readouterr().out

    path.write_bytes(b"existing file")
    with pytest.raises(SystemExit) as error:
        run_cli(argv)
    assert error.value.code == 1
    assert path.read_bytes() == b"existing file"
    assert "output file already exists" in capsys.readouterr().err
