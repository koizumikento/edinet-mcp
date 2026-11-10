# edinet-mcp

金融庁EDINETの提出書類一覧を日付で取得し、提出者や書類種別で絞れます。書類管理番号、提出日時、取下げ・開示の区分を確認できます。

[uv](https://docs.astral.sh/uv/) と Git が必要です。Python 3.12以上に対応しています。[EDINETの案内](https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/WZEK0090_001.html)に従ってAPIキーを発行し、例の `YOUR_EDINET_API_KEY` を手元の設定で差し替えてください。

## MCPクライアントに登録する

### Codex

```sh
codex mcp add edinet-mcp --env "EDINET_API_KEY=YOUR_EDINET_API_KEY" -- uvx --python 3.12 --from git+https://github.com/koizumikento/edinet-mcp.git@main edinet-mcp
codex mcp list
```

新しいセッションで `/mcp` を開いて接続を確認できます。デスクトップ版ではMCP設定画面で、下のJSON例と同じコマンド・引数・環境変数を指定できます。

### Claude Desktop / Cursor

- Claude Desktop（Windows） `%APPDATA%/Claude/claude_desktop_config.json`
- Claude Desktop（macOS） `~/Library/Application Support/Claude/claude_desktop_config.json`
- Cursor `.cursor/mcp.json`（プロジェクト内）

設定ファイルの `mcpServers` に項目を追加して、クライアントを再起動してください。`uvx` が見つからない場合は実行ファイルの絶対パスを指定します。

```json
{
  "mcpServers": {
    "edinet-mcp": {
      "command": "uvx",
      "args": [
        "--python",
        "3.12",
        "--from",
        "git+https://github.com/koizumikento/edinet-mcp.git@main",
        "edinet-mcp"
      ],
      "env": {
        "EDINET_API_KEY": "YOUR_EDINET_API_KEY"
      }
    }
  }
}
```

> 2026年6月30日のEDINET提出書類から、有価証券報告書を3件探して。

## MCPツール

### `list_filings`

`filing_date` は `YYYY-MM-DD` の一覧ファイル日付です。`filer` は提出者名・EDINETコード・証券コードの部分一致です。`document_type` は3桁の書類種別コードで、例の `120` は有価証券報告書です。結果は一覧のメタデータで、続きがあれば `next_offset` を返します。

## CLIで使う

PowerShellでは `$env:EDINET_API_KEY = "YOUR_EDINET_API_KEY"`、macOSやLinuxでは `export EDINET_API_KEY="YOUR_EDINET_API_KEY"` を先に実行します。APIキーは手元で管理してください。

```sh
uvx --python 3.12 --from git+https://github.com/koizumikento/edinet-mcp.git@main edinet-mcp list-filings --date 2026-06-30 --document-type 120 --limit 3
```

結果は標準出力にUTF-8のJSONで返ります。

## Pythonから呼び出す

```sh
git clone https://github.com/koizumikento/edinet-mcp.git
cd edinet-mcp
uv sync --locked
```

```python
import asyncio

from edinet_mcp import list_filings

print(asyncio.run(list_filings("2026-06-30", document_type="120", limit=3)))
```

既にイベントループがある場合は関数を直接 `await` してください。

## 出典と利用条件

コードはMIT Licenseです。金融庁EDINET API v2の書類一覧APIを使っています。[公式仕様](https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/download/ESE140206.pdf)・[EDINET利用規約](https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/WZEK0030.html)

## 開発

```sh
uv sync --locked
uv run ruff check .
uv run ty check
uv run pytest
uv build
```
