# MCP 伺服器參考（stdio）

`server/mcp_server.py` 以 stdio 講 MCP：JSON-RPC 2.0、一行一則訊息。不需要先啟動網頁面板，不連網、不需 pip 套件。對外工具與 HTTP API 相同：`list_inbox`、`brain_board`、`search_brain`、`persona`、`save_draft`。

## 1. 傳輸與訊息格式

- 傳輸：stdin／stdout，一行一個 JSON-RPC 2.0 訊息。
- 方法：`initialize`、`tools/list`、`tools/call`、`ping`。
- 前四項工具只讀本機快取；`save_draft` 只寫本機 SQLite 草稿表，絕不寄出。

請求範例（`initialize`）：

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{}}}
```

## 2. 方法

### `initialize`

| 參數 | 型別 | 說明 |
|---|---|---|
| `protocolVersion` | string | 例如 `2025-06-18` |
| `capabilities` | object | 客戶端能力 |

回應內容（result）的確切欄位（待確認）；客户端應依回傳的 protocolVersion 續談。

### `tools/list`

回傳工具陣列。每支工具至少有 `name`、`description`、`inputSchema`；schema 細節（待確認）。

### `tools/call`

| 參數 | 型別 | 說明 |
|---|---|---|
| `name` | string | 工具名稱 |
| `arguments` | object | 該工具參數（各工具 schema 待確認） |

### `ping`

連通測試。

## 3. 工具清單

| 工具 | 讀寫 | 說明 |
|---|---|---|
| `list_inbox` | 唯讀 | 列出本機收件匣 |
| `brain_board` | 唯讀 | Second Brain 看板 |
| `search_brain` | 唯讀 | 搜尋本機卡片 |
| `persona` | 唯讀 | 「更了解你」人格 |
| `save_draft` | 寫入 | 只寫本機 SQLite 草稿表；唯一寫入工具；不寄信 |

## 4. 客戶端設定

Claude Desktop（`claude_desktop_config.json`）與 Cursor（`~/.cursor/mcp.json` 或專案內 `.cursor/mcp.json`）使用同一段設定；把路徑換成你的 checkout：

```json
{
  "mcpServers": {
    "toopowerinbox": {
      "command": "python3",
      "args": ["/path/to/openinbox/server/mcp_server.py"],
      "env": { "OPENINBOX_ROOT": "/path/to/openinbox" }
    }
  }
}
```

`OPENINBOX_ROOT` 可省略（預設為 checkout 根目錄）。示範模式下啟動時會載入 `fixtures/` 示範資料。

## 5. 終端機快速驗證

```
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{}}}' '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | python3 server/mcp_server.py
```

## 6. 安全邊界

- stdio 模式不提供網路服務，也不應連到正式外部系統。
- 沒有任意檔案讀取、路徑穿越或寄送能力。
- `save_draft` 是唯一寫入，且只碰本機草稿表。
- 未來若新增唯讀工具（例如搜尋信件、聯絡人），應採向後相容方式新增，舊客户端可安全忽略新欄位。
