# MCP 介面參考

`server/mcp_server.py` 以標準輸入／輸出提供 MCP 風格的 JSON-RPC 2.0 介面。每行是一則 JSON 訊息；此模式不需要啟動 HTTP 面板。

## JSON-RPC 方法

| 方法 | 可確認用途 |
|---|---|
| `initialize` | 初始化協定連線。 |
| `tools/list` | 列出可呼叫工具。 |
| `tools/call` | 執行指定工具。 |
| `ping` | 探測服務回應。 |

README 的啟動範例使用 `protocolVersion`、`capabilities` 與請求 `id`。協定版本協商細節、錯誤碼及每個 JSON-RPC 方法的完整 schema，須以 `server/mcp_server.py` 實作為準；該檔案內容未包含在本次提供的原始碼中。

## 已知工具

| 工具名稱 | 可確認用途 |
|---|---|
| `list_inbox` | 讀取本機快取收件匣。 |
| `brain_board` | 讀取本機 Second Brain 看板。 |
| `search_brain` | 搜尋本機 Second Brain。 |
| `persona` | 讀取本機人格資料。 |
| `save_draft` | 將草稿寫入本機 SQLite 草稿表；不會寄出郵件。 |

各工具的輸入 schema、分頁方式、回應 schema 與錯誤格式，尚待核對 MCP 實作。MCP 工具不提供任意檔案讀取或寄送能力。

## 啟動方式

以 Python 執行 MCP server，並讓 MCP 客戶端將程序的 stdin/stdout 作為傳輸通道。`OPENINBOX_ROOT` 可作為環境變數指定 checkout 根目錄；省略時使用預設 checkout 根目錄。

## JSON-RPC 範例

下例只展示初始化請求的線路形狀，不包含帳號、憑證或郵件內容：

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"<MCP protocol version>","capabilities":{}}}
```

列出工具的請求：

```json
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
```

## 已知限制

- MCP server 以 stdio 執行，與 HTTP API 分開。
- 工具讀取本機快取；`save_draft` 是已知的本機寫入工具。
- 初始化時示範模式可載入 fixtures；具體啟動副作用應以 MCP server 與核心初始化實作核對。
- 完整工具參數及錯誤參考尚待取得 `server/mcp_server.py` 原始碼後補齊。
