# 設定參考

本文件只寫設定項「名稱」與用途，不寫任何值。所有機敏內容（密碼、API key）一律經由環境變數注入，不寫入檔案、不寫入文件。

## 1. `accounts.json`（gitignored）

由 `accounts.example.json` 於安裝時複製；已存在時不覆寫。

| 欄位 | 型別 | 說明 |
|---|---|---|
| `mode` | string | `demo`（預設，載入 `fixtures/`）｜`live`（真實帳號） |
| `accounts` | array | 帳號物件清單 |
| `calendars` | array | 行事曆來源（可為空） |

帳號物件：

| 欄位 | 說明 |
|---|---|
| `email` | 帳號信箱；也用来推導預設密碼環境變數名 |
| `platform` | 平台標記（例如 `gmail`） |
| `driver` | `demo`｜`gog`（Gmail）｜`gsk`（Genspark CLI 傳輸）｜`imap`（唯讀） |
| `label` | 面板顯示名稱 |
| `provider` | IMAP 預設主機捷徑：`icloud`｜`fastmail`｜`yahoo`｜`zoho` |
| `host`／`port` | 其他 IMAP 主機；port 預設 993 |
| `security` | `starttls` 可用；`none` 只限本機 loopback |
| `username` | 選填登入名稱 |
| `mailbox` | 選填，預設 `INBOX` |
| `password_env` | 指定讀取密碼的「環境變數名稱」 |

密碼規則：

- 只從環境變數讀：`password_env` 指定的變數；未指定時讀 `TPI_IMAP_PASSWORD_<信箱大寫、非英數字元轉 _>`。
- `accounts.json` 內出現明文 `password` 欄位會被拒絕。
- 文件與程式都不保存、不回傳密碼值。

## 2. `agent.json`（gitignored）

BYO Agent 驅動設定，欄位見 [agent-bridge.md](agent-bridge.md)。API key 只以 `api_key_env` 指定環境變數名稱。

## 3. `rules.json`（gitignored）

使用者自訂郵件規則；搭配規則 dry-run 使用。規則不得直接寄信。

## 4. 環境變數（只列名稱）

| 變數 | 用途 |
|---|---|
| `OPENINBOX_ROOT` | checkout 根目錄（`run.sh` 與 MCP 使用；MCP 可省略） |
| `OPENINBOX_PORT` | HTTP 埠，預設 8770 |
| `OPENINBOX_NO_BROWSER` | 設定的話啟動不開瀏覽器（雲端主機用） |
| `TPI_IMAP_PASSWORD_<信箱>` | 依帳號信箱推導的 IMAP 密碼變數名 |
| `TPI_IMAP_PASSWORD` | 未推導時的通用 IMAP 密碼變數名 |
| `<api_key_env 指定者>` | `agent.json` 裡 `api_key_env` 指向的變數名 |

變數「值」不寫在檔案、不寫在文件、不進日誌。

## 5. 本機資料檔（`data/`，gitignored）

| 路徑 | 內容 |
|---|---|
| `data/openinbox.db` | SQLite：信件、行事曆、草稿、狀態、搜尋索引等 |
| `data/usage.jsonl` | token 用量；不記提示詞、回答或金鑰 |
| `data/contacts.json` | 本機 CRM 聯絡人 |
| `data/skills.json` | 技能開關與設定 |
| `data/slides/` | 技能產生的本機 HTML 投影片 |
| `data/deliverables/` | Agent 協作成果（md／html／json） |

## 6. `vault/`（gitignored）

| 路徑 | 內容 |
|---|---|
| `vault/persona.json`、`vault/persona.md` | 人格資料 |
| `vault/index.json` | Second Brain 索引 |
| `vault/cards/*.md` | 衍生卡片與使用者筆記（只保留 `.gitkeep`） |

## 7. Git 狀態速查

`accounts.json`、`agent.json`、`rules.json`、`data/`、`vault/persona.*`、`vault/index.json`、`vault/cards/*.md`、`*.db`、`*.log` 皆在 `.gitignore` 內；提交前不應出現以上檔案。
