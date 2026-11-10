# edinet-mcp

金融庁EDINETの提出書類一覧を日付で取得し、提出者や書類種別で絞れます。一覧で得た書類管理番号からPDFやCSVのZIPを取得できます。

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

`filing_date` は `YYYY-MM-DD` の一覧ファイル日付です。`filer` は提出者名・EDINETコード・証券コードの部分一致です。`document_type` は3桁の書類種別コードで、例の `120` は有価証券報告書です。結果は書類管理番号、提出日時、取下げ・開示の区分、`pdf_flag` と `csv_flag` を含みます。形式が利用可能な場合、該当のフラグは `"1"` です。続きがあれば `next_offset` を返します。

### `get_filing_document`

一覧から得た `document_id` を指定します。`format` は `pdf`（既定）または `csv` です。PDFはEDINETの検索結果から表示できる書類本体です。CSVはEDINETがXBRLから変換したデータを格納したZIPで、展開せず原本を返します。開示状況や形式によって取得できない書類があります。

EDINETの応答はPDFが `application/pdf`、CSVのZIPが `application/octet-stream` です。このツールはZIPを `application/zip` として返します。MCPの埋め込みリソースはこのツールの上限として原本2 MiBまでです。クライアントがこの形式を表示できない場合や、2 MiBを超える場合はCLIを使ってください。

## CLIで使う

PowerShellでは `$env:EDINET_API_KEY = "YOUR_EDINET_API_KEY"`、macOSやLinuxでは `export EDINET_API_KEY="YOUR_EDINET_API_KEY"` を先に実行します。APIキーは手元で管理してください。

```sh
uvx --python 3.12 --from git+https://github.com/koizumikento/edinet-mcp.git@main edinet-mcp list-filings --date 2026-06-30 --document-type 120 --limit 3
uvx --python 3.12 --from git+https://github.com/koizumikento/edinet-mcp.git@main edinet-mcp get-filing-document --document-id S1234567 --format pdf --output filing.pdf
uvx --python 3.12 --from git+https://github.com/koizumikento/edinet-mcp.git@main edinet-mcp get-filing-document --document-id S1234567 --format csv --output filing-csv.zip
```

例の `S1234567` は取得したい書類の管理番号に置き換えます。書類は最大32 MiBまで、指定した新規ファイルに保存します。結果は標準出力にUTF-8のJSONで返ります。

## Pythonから呼び出す

```sh
git clone https://github.com/koizumikento/edinet-mcp.git
cd edinet-mcp
uv sync --locked
```

```python
import asyncio

from edinet_mcp import get_filing_document, list_filings

print(asyncio.run(list_filings("2026-06-30", document_type="120", limit=3)))
document = asyncio.run(get_filing_document("S1234567", format="csv"))
print(document.metadata)
```

書類のバイト列は `document.content` から取得できます。取得上限は32 MiBです。`max_bytes` で上限を小さくできます。既にイベントループがある場合は関数を直接 `await` してください。

## 出典と利用条件

コードはMIT Licenseです。金融庁EDINET API v2の書類一覧APIと書類取得APIを使っています。[公式仕様](https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/download/ESE140206.pdf)・[EDINET利用規約](https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/WZEK0030.html)

## 開発

```sh
uv sync --locked
uv run ruff check .
uv run ty check
uv run pytest
uv build
```
