# HTTP API 參考

所有端點由 `server/app.py`（核心）與 `server/features/*.py`（外掛）提供，服務只監聽 `127.0.0.1:8770`（可用 `OPENINBOX_PORT` 改埠）。除特別說明外，請求與回應皆為 JSON。

標注：（source）＝簽名由 `server/features/agents.py` 原始碼確認；（readme）＝由 README／架構文件確認；（待確認）＝快照中無完整原始碼，僅記錄用途，簽名以程式碼為準。

## 1. 端點總覽

| 方法 | 路徑 | 用途 | 來源 |
|---|---|---|---|
| GET | `/api/health` | 健康檢查 | readme |
| GET | `/api/inbox` | 統一收件匣（本機快取） | readme |
| POST | `/api/copilot` | 摘要／待辦／草稿／對話 | readme |
| GET | `/api/drafts` | 草稿列表 | readme |
| POST | `/api/draft` | 草稿建立／儲存（待確認） | readme |
| GET | `/api/v1/tools` | 列出 Agent 工具 | readme |
| GET | `/api/v1/context` | 取得人格、看板、近期信件 | readme |
| POST | `/api/v1/tools/{name}` | 呼叫單一工具 | readme |
| POST | `/api/v1/agent/run` | 內建 Agent 包裝（ask＋skill） | readme |
| GET | `/api/skills` | 技能列表與開關 | readme |
| POST | `/api/skills/run` | 執行技能 | readme |
| POST | `/api/skills/settings` | 技能開關設定 | readme |
| GET | `/api/crm/contacts` | 本機 CRM 聯絡人 | readme |
| POST | `/api/crm/contacts/update` | 新增／更新聯絡人 | readme |
| POST | `/api/crm/contacts/delete` | 刪除聯絡人 | readme |
| GET | `/api/usage` | BYOK token 用量 | readme |
| GET | `/api/providers` | 帳號、信件數、上次同步結果 | readme |
| POST | `/api/providers/check` | IMAP 連線測試（登入＋EXAMINE） | readme |
| GET | `/api/cache` | 目前快取內容 | readme |
| POST | `/api/cache/clear` | 清除本機快取（可重載示範資料） | readme |
| GET | `/api/cal/*` | 行事曆事件、檢視、free/busy、邀請草稿（待確認） | readme |
| POST | `/api/cal/feed/delete` | 移除匯入的同事 ICS feed | readme |
| GET | `/api/mobile/info` | PWA 快取清單 | readme |
| GET | `/api/features` | 已載入功能、路由、匯入錯誤 | readme |
| GET | `/api/ui-modules` | 面板要載入的 UI 模組清單 | readme |
| POST | `/api/agents/task` | 發動研究／會議準備任務 | source |
| POST | `/api/agents/mention` | thread 內 `@agent` 路由 | source |
| GET | `/api/agents/deliverables` | 成果卡片列表 | source |
| GET | `/api/agents/deliverables/{id}.{fmt}` | 取得單一成果（md／html／json） | source |
| GET | `/api/triage` | 分流視圖與摘要（待確認） | readme |
| GET | `/api/brain/*` | 第二大腦推論與修正（待確認） | readme |
| GET | `/api/search`、`/api/search/reindex` | 搜尋、重建索引（待確認） | readme |
| GET | `/api/contacts` | 聯絡人彙整（待確認） | readme |
| POST | `/api/compose/*` | 撰寫、改寫、語氣、字型（待確認） | readme |
| POST | `/api/outbox/*` | outbox 確認、排程、撤銷（待確認） | readme |

其他功能家族（`rules.py`、`followup.py`、`overnight.py`、`mailops.py`）在快照中未提供路由字串，逐一標（待確認）；文件只記錄其存在與職責，不虛構路徑。

## 2. 核心與面板

### GET `/api/health`（readme）

健康檢查。回應包含服務狀態；安裝後可用它確認伺服器活著。

```bash
curl -s http://127.0.0.1:8770/api/health
```

### GET `/api/inbox`（readme）

統一收件匣，資料來自本機 SQLite 快取，不會直接打供應商。面板三欄與分流桶皆以此為來源。

## 3. Copilot 與草稿

### POST `/api/copilot`（readme）

| 參數 | 型別 | 說明 |
|---|---|---|
| `mode` | string | `summarize`｜`todos`｜`draft`｜`chat` |
| `item_id` | string | 目標信件（模式需要時） |
| `ask` | string | 使用者提問 |
| `lang` | string | `zh-Hant`｜`en` |

回應包含結果文字；未接 LLM 時自動降級為本機啟發式並明確標示。草稿只存本機。

### 草稿端點（readme）

`GET /api/drafts` 列出草稿；`POST /api/draft` 建立／儲存。MCP 的 `save_draft` 與此共用同一個本機 SQLite 草稿表。確切方法與欄位（待確認）。

## 4. Agent v1 工具 API

給外部 Agent 的低階入口，詳見 [agent-bridge.md](agent-bridge.md)。

### GET `/api/v1/tools`（readme）

回傳可用工具清單：`list_inbox`、`brain_board`、`search_brain`、`persona`、`save_draft`。

### GET `/api/v1/context?lang=zh-Hant`（readme）

回傳人格、Second Brain 看板與近期信件，組成 context pack 的基礎。

### POST `/api/v1/tools/{name}`（readme）

以路徑指定工具名稱呼叫；body 為該工具的參數。

### POST `/api/v1/agent/run`（readme）

| 參數 | 型別 | 說明 |
|---|---|---|
| `ask` | string | 問題或指令 |
| `skill` | string | 選用，`skills/*.md` 的檔名（例如 `morning-brief`） |
| `lang` | string | `zh-Hant`｜`en` |

```bash
curl -s -X POST http://127.0.0.1:8770/api/v1/agent/run \
  -H 'Content-Type: application/json' -H 'Origin: http://127.0.0.1:8770' \
  -d '{"ask":"今天什麼要我處理？","skill":"morning-brief","lang":"zh-Hant"}'
```

## 5. 技能、CRM 與用量

詳見 [skills.md](skills.md)。

| 端點 | 說明 |
|---|---|
| `GET /api/skills` | 技能列表（含開關狀態） |
| `POST /api/skills/run` | 執行技能；關閉中的技能會拒絕執行 |
| `POST /api/skills/settings` | 開關設定，存 `data/skills.json` |
| `GET /api/crm/contacts` | 本機 CRM（`data/contacts.json`） |
| `POST /api/crm/contacts/update` | 新增／更新聯絡人 |
| `POST /api/crm/contacts/delete` | 刪除聯絡人 |
| `GET /api/usage` | token 用量（`data/usage.jsonl`）；不記提示詞、回答或金鑰 |

## 6. 帳號與同步

### GET `/api/providers`（readme）

列出帳號、各帳號信件數與上次同步結果；只回環境變數名稱，永不回密碼。

### POST `/api/providers/check`（readme）

IMAP 帳號連線測試：只登入＋`EXAMINE`，不在伺服器上留下任何變更。

## 7. 快取與外掛

### GET `/api/cache`（readme）

顯示目前快存了什麼。

### POST `/api/cache/clear`（readme）

| 參數 | 型別 | 說明 |
|---|---|---|
| `reseed` | boolean | `true` 時重新載入示範信件 |

清除郵件快取、示範／快取行事曆、Agent 回合與衍生卡片、衍生人格與索引；保留草稿、手寫卡片、本機建立或匯入的行事曆資料與邀請草稿。

### GET `/api/features`（readme）

已載入功能、路由與匯入錯誤。外掛是受信任本機程式碼，不是沙箱。

### GET `/api/ui-modules`（readme）

面板據此載入 `ui/modules/*.js`。

## 8. 行事曆與行動端

- `POST /api/cal/feed/delete`（readme）：body `{"id": N}`，移除匯入的同事 ICS feed；本機事件不受影響。
- `GET /api/mobile/info`（readme）：列出 service worker 確實快取的靜態檔；不快取任何 `/api/*`。

## 9. Agent 協作端點（source）

以下簽名與行為直接來自 `server/features/agents.py`。所有端點都會先做本機來源檢查，非本機來源會被拒絕。

任務種類（`TASK_KINDS`）：`research_person`（人物研究）、`research_company`（公司研究）、`meeting_prep`（會議準備）。

### POST `/api/agents/task`

發動一個任務，成果會同時存成 Markdown／HTML／JSON 卡片。

請求 body：

| 欄位 | 型別 | 必填 | 說明 |
|---|---|---|---|
| `kind` | string | 是 | 三種任務種類之一 |
| `target` | string | 條件 | 研究對象；`strip()` 後截斷 120 字元。與 `ask` 至少留一 |
| `ask` | string | 條件 | 補充說明；截斷 1000 字元 |
| `lang` | string | 否 | `zh-Hant`｜`en`，影響介面與成品語系 |

錯誤：

| 狀態碼 | 情況 | 回應 |
|---|---|---|
| 400 | `kind` 不在清單 | `{"error": "unknown kind", "kinds": [...]}` |
| 400 | `target` 與 `ask` 皆空 | `{"error": "target or ask required"}` |

成功回應（200）：

| 欄位 | 說明 |
|---|---|
| `deliverable` | 卡片 metadata：`id`、`title`、`kind`、`target`、`lang`、`created`、`driver`、`fallback` |
| `text` | 成品內文 |
| `driver` | 實際使用的驅動（`local`／`openai_compatible`／`cli`／`http`） |
| `fallback` | 是否退回本機啟發式 |
| `error` | 失敗標籤或 `null`；只含例外類別與 HTTP 狀態，不含例外訊息 |
| `sources` | 本機資料來源：`id`、`subject`、`from`、`date`、`snippet` |

```bash
curl -s -X POST http://127.0.0.1:8770/api/agents/task \
  -H 'Content-Type: application/json' -H 'Origin: http://127.0.0.1:8770' \
  -d '{"kind":"research_person","target":"Samira Ortiz","lang":"zh-Hant"}'
```

### POST `/api/agents/mention`

路由一封 thread 訊息。三種用法由 body 決定：

| body | `via` | 行為 |
|---|---|---|
| 只有 `text` | `text` | 解析 `@agent` 提及；沒有觸發詞回 `triggered: false` |
| `text`＋`email_id` | `thread` | 在開啟的 thread 內提及；該封信排在 sources 第一位；bare `@agent` 以寄件人為對象 |
| 只有 `email_id` | `email` | 讀本機快取內該信：收件者含 agent 別名或內文有 `@agent` 才觸發 |

錯誤：`email_id` 找不到 → `404 {"error": "not found"}`。

未觸發回應：`{"triggered": false, "via": …, "hint": …}`（`hint` 為 `not addressed to the agent` 或 `no @agent mention`）。

觸發回應：`{"triggered": true, "via", "mention": {"kind","target","word","ask"}, "deliverable", "text", "driver", "fallback", "error", "sources"}`。

別名 `agent@example.com` 只是路由詞，本模組從不讀信或送信到它。

### GET `/api/agents/deliverables`

| query | 型別 | 說明 |
|---|---|---|
| `limit` | int | 預設 50，上限 200，下限 1；非數字回落為 50 |

回應：`{"deliverables": [卡片metadata…], "alias": "agent@example.com"}`，依 `created` 倒序。

### GET `/api/agents/deliverables/{id}.{fmt}`

| 部分 | 規則 |
|---|---|
| `id` | 必須符合 `^[a-z0-9][a-z0-9-]{2,80}$`，避免路徑穿越 |
| `fmt` | `md`（預設）｜`html`｜`json` |

回傳原始位元組與對應 content-type；id 不合法或檔案不存在回 `404 {"error": "not found"}`。HTML 內容全跳絕、無腳本、無外部資源，前端以 sandbox iframe 預覽。

## 10. 其餘功能家族（待確認）

`/api/triage`、`/api/brain/*`、`/api/search`、`/api/search/reindex`、`/api/contacts`、`/api/compose/*`、`/api/outbox/*` 與 rules／followup／overnight／mailops 家族，在提供的檔案中只確認了存在與職責（見 `docs/fmb/ARCHITECTURE.md`），確切方法、參數與回應 schema 待補原始碼後增補。
