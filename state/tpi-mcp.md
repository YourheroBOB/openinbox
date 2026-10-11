# tpi-mcp

goal: openinbox 通用 MCP 伺服器：新增 server/mcp_server.py（stdio JSON-RPC 2.0，MCP initialize／tools/list／tools/call），把 server/agent_bridge.py 的 TOOLS（list_inbox、brain_board、search_brain、persona、save_draft）包成 MCP 工具；save_draft 只存本機草稿；附 tests/test_tpi_mcp_*.py 與 README 設定範例。
status: done
next: 無必要後續；可選：若 main 之後加入 server/features/ 外掛機制，再評估是否把 MCP 工具註冊改為讀 features。

## 內容
- server/mcp_server.py：stdio、逐行 JSON-RPC 2.0；initialize（協商 2025-06-18／2025-03-26／2024-11-05）、ping、tools/list、tools/call、batch；通知不回應；錯誤碼 -32700／-32600／-32601／-32602／-32603；工具參數錯誤以 isError 回傳。
- 工具清單由 agent_bridge.TOOLS 依序產生，附 inputSchema、雙語 title/description、annotations；執行走 agent_bridge.invoke_tool。save_draft 只寫本機 SQLite drafts 表，回傳 sent:false。
- 不連網、只用標準函式庫；stdout 只輸出協定訊息，雜訊導向 stderr。
- app.py、ui/ 未改動；main 尚無 server/features/ 機制，故不需掛勾。
- README.md／README.zh-Hant.md 新增 MCP 一節（Claude Desktop／Cursor 設定，路徑用 /path/to/openinbox 佔位）。
- CI smoke.yml 加一步 `python3 -m unittest discover -s tests -v`。

## log
- 2026-10-11 13:40 (UTC+8) 新增 mcp_server.py、tests/test_tpi_mcp_stdio.py（subprocess 實際驅動 stdio，暫存 OPENINBOX_ROOT）、tests/test_tpi_mcp_policy.py（禁寄信字樣、僅標準函式庫、無部署設定、README 佔位、fixture 網域）；驗證：`python3 -m unittest discover -s tests` 21 tests OK、手動 printf 管線 initialize/tools/list/save_draft 正常、app.py 於 8799 啟動 /api/health 正常；scripts/smoke.sh 不存在。
