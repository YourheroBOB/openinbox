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
- 2026-10-11 14:32 (UTC+8) review pass（合併驗收）：`git fetch origin main` 後確認 origin/main 已是 HEAD 祖先、工作區乾淨無衝突殘留；分支相對 main 只動 smoke.yml（unittest 加 -v）、雙語 README MCP 一節、server/mcp_server.py、tests/test_tpi_mcp_*.py、本檔，app.py／ui／agent_bridge.py／server/features／STATE.md 與 main 一致。驗證：`python3 -m unittest discover -s tests` 72 tests OK（MCP 21 tests OK、無 skip）；`bash scripts/smoke.sh` exit 0；以暫存 OPENINBOX_ROOT 手動 stdio 管線跑 initialize／通知／tools/list／五工具皆成功，save_draft 只寫暫存 SQLite drafts 並回 sent:false，-32602／-32601／-32700 正確；禁寄信字樣、部署設定檔、workflow 禁字、非標準函式庫匯入皆無。本輪無需修改程式。
- 2026-10-11 14:30 (UTC+8) 合併 origin/main（tpi-foundation：tests/、scripts/smoke.sh、server/features/ 外掛、/api/cache、STATE.md 等）進 agent/tpi-mcp。唯一衝突 .github/workflows/smoke.yml，保留 `python3 -m unittest discover -s tests -v` 那步；app.py、ui/index.html、agent_bridge.py 與 main 完全一致（MCP 不走 HTTP feature route，獨立 stdio 入口，不需掛勾）。README 雙語兩側章節皆保留。驗證：`python3 -m unittest discover -s tests` 72 tests OK；`bash scripts/smoke.sh` exit 0；掃描禁寄信字樣／部署設定檔／workflow 字樣皆無；root STATE.md 未動。
- 2026-10-11 13:40 (UTC+8) 新增 mcp_server.py、tests/test_tpi_mcp_stdio.py（subprocess 實際驅動 stdio，暫存 OPENINBOX_ROOT）、tests/test_tpi_mcp_policy.py（禁寄信字樣、僅標準函式庫、無部署設定、README 佔位、fixture 網域）；驗證：`python3 -m unittest discover -s tests` 21 tests OK、手動 printf 管線 initialize/tools/list/save_draft 正常、app.py 於 8799 啟動 /api/health 正常；scripts/smoke.sh 不存在。
- 2026-10-11 13:33 (UTC+8) review pass：重跑 `python3 -m unittest discover -s tests` 21 tests OK；手動 stdio 管線五工具＋錯誤碼（-32602／-32601／-32700）正常，草稿只進暫存 OPENINBOX_ROOT 的 SQLite；以官方 MCP Inspector CLI 套 README 的 mcpServers 設定實測 tools/list 與 save_draft／list_inbox／brain_board 皆成功；app.py 於 8799 跑 smoke.yml 同款檢查通過；禁字／部署設定／workflow 字樣／非標準函式庫匯入皆無，app.py／ui／既有模組未改。小修：整數參數接受 2.0 這類整值浮點（2.5 仍報錯），測試草稿收件人改 example.com。
