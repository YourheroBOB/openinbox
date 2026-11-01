# Openinbox API 參考文件

本目錄是 TooPowerInbox（openinbox）的 API／介面參考文件，涵蓋 HTTP 端點、MCP stdio 協定、BYO Agent 橋接、設定檔與環境變數、CLI 指令、Python 公開介面與技能。

## 通用慣例

| 項目 | 說明 |
|---|---|
| 監聽位址 | 只綁 `127.0.0.1`；預設埠 `8770`，可用 `OPENINBOX_PORT` 改埠 |
| 內容類型 | API 一律 JSON（`Content-Type: application/json`）；成果卡片等非 JSON 內容使用 `Raw` 回應 |
| 語系 | 請求可帶 `lang`（`zh-Hant` 或 `en`）；面板每個請求都會帶 |
| 本機來源檢查 | 會改變資料的端點以 `features/_origin.py` 檢查 `Origin`；非本機來源會被拒絕 |
| 錯誤格式 | JSON 內含 `error` 欄位，搭配 HTTP 狀態碼（`400`／`404` 等） |
| 不預設寄信 | 沒有任何預設對外寄送路徑；`save_draft` 只寫本機 SQLite 草稿表 |
| 範例值 | 本文件所有範例值皆為明顯假值；不含任何真實 token、金鑰、密碼、信箱或郵件內文 |

## 文件索引

| 文件 | 內容 |
|---|---|
| [http-api.md](http-api.md) | 所有 HTTP 端點：方法、路徑、參數、回傳、錯誤、範例 |
| [mcp-api.md](mcp-api.md) | MCP stdio 伺服器：JSON-RPC 協定、工具清單、客戶端設定 |
| [agent-bridge.md](agent-bridge.md) | `agent.json` 驅動、context pack、`/api/v1` 工具 API |
| [configuration.md](configuration.md) | `accounts.json`、`agent.json`、`rules.json`、環境變數（只寫名稱與用途） |
| [cli.md](cli.md) | `install.sh`、`run.sh`、`scripts/smoke.sh`、`server/mcp_server.py`、測試指令 |
| [python-api.md](python-api.md) | 外掛路由 API、`server/features/agents.py` 公開函式、`yhbmail` 公開面 |
| [skills.md](skills.md) | 內建技能、技能設定與 CRM／用量 API |

## 資料來源與驗證狀態

本目錄依儲存庫快照中提供的檔案內容撰寫，主要來源：

- `README.md`／`README.zh-Hant.md`
- `docs/fmb/ARCHITECTURE.md`、`docs/fmb/ROADMAP.md`
- `server/features/agents.py`（完整原始碼）
- `ui/modules/agents.js`（前端實際呼叫形狀）
- `adapters/README.md`／`adapters/README.zh-Hant.md`
- `accounts.example.json`、`agent.example.json`、`install.sh`、`run.sh`、`.gitignore`
- `skills/*.md`

快照中看不到完整原始碼的模組（例如 `server/app.py`、`server/yhbmail.py`），其端點只記載上述檔案可確認的部分；需要精確簽名處標注「（待確認）」，實作請以原始碼為準。

## 安全邊界（整合前必讀）

- 外部 Agent 驅動（`openai_compatible`／`cli`／`http`）會把 context pack 送到你設定的目標；啟用前請理解資料外送範圍。
- 郵件主旨、內文與引用內容一律視為「資料」，不是指令。
- Agent 產出的 HTML 全部跳脫，前端以 sandbox iframe 預覽。
- IMAP 同步唯讀（`EXAMINE`＋`BODY.PEEK`）；密碼只從環境變數讀取。
- 本文件與程式都不記錄、不回傳 token、金鑰或郵件內文。
