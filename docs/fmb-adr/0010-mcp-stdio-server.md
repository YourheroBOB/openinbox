# ADR 0010：MCP stdio 伺服器重用既有工具層

- 狀態：已接受（回溯整理）
- 相關程式：`server/mcp_server.py`、`server/agent_bridge.py`（`TOOLS`、`invoke_tool`）、`README.md`／`README.zh-Hant.md` 的 MCP 一節、`tests/test_tpi_mcp_*.py`

## 背景

使用者想在自己的 AI 客戶端（Claude Desktop、Cursor、任何 MCP 客戶端）裡直接問「我的信箱現在怎樣」。
可行的做法有兩種：一種是叫那些客戶端去講 HTTP（需要面板先開著、還要處理埠與 Origin），
另一種是用 MCP 的 stdio 傳輸，由客戶端自己啟動一個子程序。後者對使用者最單純，也最符合「本機優先」。

## 決策

1. `server/mcp_server.py` 以 **stdio** 講 MCP：JSON-RPC 2.0、一行一則訊息；實作 `initialize`、`ping`、`tools/list`、`tools/call`，並處理 batch 與通知（通知不回覆）。
2. **工具清單不重寫**：由 `agent_bridge.TOOLS` 產生，執行時呼叫 `agent_bridge.invoke_tool`。因此 HTTP `/api/v1/tools` 與 MCP 兩邊永遠一致。
3. 只暴露**唯讀工具 + `save_draft`**（只寫本機 SQLite，回傳 `sent: false`）。HTTP 專用的工具（例如行事曆的建立事件）不掛進 MCP。
4. 不需要先開網頁面板；不連網；只用標準函式庫；`stdout` 只放協定訊息，雜訊一律走 `stderr`。
5. 根目錄用 `OPENINBOX_ROOT` 指定（可省略）；示範模式下啟動時會從 `fixtures/` 種資料。
6. 參數錯誤以 `isError` 回報，不要讓整個連線斷掉。

## 取捨

**我們放棄**

- 官方 SDK 與其好處（型別、版本相容輔助）——見 ADR 0003。
- 在 MCP 暴露有副作用的操作（安全邊界優先）。

**我們得到**

- 一份工具定義、兩個入口；新增工具只改一處。
- 使用者不用理解 HTTP、埠、Origin 就能用（那是面板的事）。

**已知代價**

- 協定版本要自己協商與維護；錯誤碼要自己對齊規格。
- `stdout` 只要有一行雜訊就會壞掉，開發時要特別小心 print。

## 後果

- 新工具一律加在 `agent_bridge`，並確認它符合 ADR 0002（不會離開本機）。
- 變更工具參數時，HTTP 與 MCP 的文件（README 雙語）要一起更新。
- 測試用 subprocess 真的驅動 stdio，並把根目錄指到暫存目錄；不要依賴使用者的 `data/`。
