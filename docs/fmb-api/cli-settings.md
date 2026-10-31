# CLI 與設定參考

本頁僅記錄可由 README、shell 腳本及設定範例確認的命令與設定名稱。設定項只列名稱，不列值。`scripts/overnight.py` 等未提供實作的 CLI 不猜測其選項。

## CLI 命令

### 安裝：`./install.sh`

檢查 Python 版本，建立必要的本機資料目錄，並在缺少設定檔時建立初始設定。參數與退出碼細節未由提供內容說明。

### 啟動：`./run.sh`

從 repo 根目錄啟動 `server/app.py`。腳本會設定執行根目錄及 HTTP 埠相關環境變數。沒有提供命令列旗標契約。

可用環境變數名稱見下方「執行環境變數」。

### MCP stdio：`python3 server/mcp_server.py`

以 stdio 啟動 MCP 服務，讀取 JSON-RPC 請求並輸出回應。協定方法見 [MCP 介面](mcp.md)。

### 單元測試：`python3 -m unittest discover -s tests`

執行 `tests/` 下的 unittest。這是測試命令，不是產品 CLI。

### Smoke 測試：`scripts/smoke.sh`

在本機執行 smoke 檢查。參數與退出碼以腳本實作為準。

### 未能確認的命令

repo 清單含 `scripts/overnight.py`，但未提供其內容，因此本文件不宣稱其命令名稱、參數或回傳狀態。其他 Python 模組的可執行入口也未經完整原始碼核對。

## 執行環境變數

以下列出名稱，不列值：

- `OPENINBOX_ROOT`
- `OPENINBOX_PORT`
- `OPENINBOX_NO_BROWSER`
- `TPI_IMAP_PASSWORD_<EMAIL_IDENTIFIER>`
- `TPI_IMAP_<ACCOUNT_PASSWORD_VARIABLE>`

`TPI_IMAP_PASSWORD_<EMAIL_IDENTIFIER>` 的 email identifier 會依實作規則轉成大寫並將非英數字元換成底線。IMAP 密碼應由環境變數提供；帳號設定中的明文 `password` 會被拒絕。`password_env` 是指向環境變數名稱的設定欄位，不是密碼欄位。

## 設定檔與設定項名稱

### `accounts.json`

可由公開說明確認的頂層欄位名稱：

- `mode`
- `accounts`
- `calendars`

`accounts` 項目可見的欄位名稱：

- `email`
- `platform`
- `driver`
- `label`
- `provider`
- `host`
- `port`
- `security`
- `username`
- `mailbox`
- `password_env`

公開說明提及的郵件驅動名稱：`demo`、`gog`、`gsk`、`imap`。IMAP 的 provider、TLS、安全限制及預設行為詳情，請以 `server/features/imap.py` 實作為準。

### `agent.json`

可由設定範例確認的欄位名稱：

- `driver`
- `openai_compatible`
- `openai_compatible.base_url`
- `openai_compatible.model`
- `openai_compatible.api_key_env`
- `cli`
- `cli.command`
- `cli.timeout_sec`
- `http`
- `http.url`
- `http.timeout_sec`

公開說明中的驅動名稱：`local`、`openai_compatible`、`cli`、`http`。設定中應以 `api_key_env` 指向環境變數名稱，不應把 API key 直接寫入設定檔。此文件不列任何設定值。

### 其他本機設定名稱

- `rules.json`：自訂郵件規則。
- `data/skills.json`：技能開關設定。
- `data/contacts.json`：本機 CRM 聯絡人資料。
- `data/usage.jsonl`：BYOK token 用量紀錄。
- `data/slides/`：技能產生的投影片。
- `data/deliverables/`：Agent 協作成果卡片。

這些路徑是設定或資料項名稱，不代表應將其中的個人資料、郵件內容或憑證複製到文件。
