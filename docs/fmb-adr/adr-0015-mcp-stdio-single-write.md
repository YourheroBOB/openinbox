# ADR-0015：MCP——獨立 stdio 程序、五工具、單一寫入

- 狀態：已接受（現況仍有效）
- 日期：事後補建（原始決策日未記錄）
- 影響範圍：`server/mcp_server.py`、`agent_bridge` 工具集、文件
- 相關：ADR-0003、ADR-0007、ADR-0005；ROADMAP 第 4 項

## 背景

Claude Desktop、Cursor 等 MCP 客戶端要能讀取這台機器的信箱腦。若為此另開 HTTP 埠，就得多管
一份連線、認證與版本相容（ADR-0007）；而寫入能力每多一個，誤用與提示注入的風險就高一分。

## 決策

1. `server/mcp_server.py` 是**獨立的 stdio 程序**，不需要先啟動網頁面板，也不開任何網路埠。
2. 協定：JSON-RPC 2.0、**一行一則訊息**；支援 `initialize`、`tools/list`、`tools/call`、`ping`。
3. 工具集與 HTTP API 對齊，目前固定五個：`list_inbox`、`brain_board`、`search_brain`、
   `persona`、`save_draft`。
4. 前四個**唯讀**本機快取；`save_draft` 是**唯一寫入**，且只寫 SQLite 草稿表，絕不寄出。
5. `OPENINBOX_ROOT` 可省略（預設為 checkout 根目錄）；設定只需一段 JSON（Claude Desktop 與
   Cursor 共用）。
6. 不連網、不需 pip、不引入 MCP SDK；示範模式下啟動時載入 `fixtures/`。
7. 擴充（如 `search_mail`、`list_contacts`）排入 ROADMAP 第 4 項，並要求向後相容：
   `tools/list` 可加版本與能力旗標，舊客戶端忽略新欄位。

## 取捨

| 考慮過的做法 | 為什麼沒有選 |
|---|---|
| HTTP MCP 傳輸 | 需要埠、認證與部署設定，違反 loopback-only 定位 |
| 開放更多寫入工具（寄信、刪信、改規則） | 違反最小權限與 ADR-0003 的人工確認原則 |
| 依賴官方 MCP SDK | 違反零 pip；stdio 手寫協定已可驗證 |

## 後果

**正面**

- 外部 Agent 開箱可用；一段 JSON 設定即可，攻擊面僅限本機行程。
- 協定簡單可測：`printf … | python3 server/mcp_server.py` 就能驗證。

**負面／代價**

- 工具集目前固定，新工具要同步維護 HTTP 與 MCP 兩處。
- stdio 除錯比 HTTP 難；客戶端版本差異要靠協定測試覆蓋。

## 證據

- `README.md`「MCP server」段：stdio、JSON-RPC 2.0 一行一則、五工具、`save_draft` 只寫本機
  草稿表、`OPENINBOX_ROOT` 預設、終端機驗證指令。
- `docs/fmb/ARCHITECTURE.md` 第 5.8 節。
- `adapters/README.md`：「Send is not exposed.」
- `docs/fmb/ROADMAP.md` 第 4 項（擴充唯讀工具、能力協商、協定測試）。
