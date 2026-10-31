# HTTP API 參考

本頁分為兩部分：第一部分是可由提供的路由實作確認的 Agent 協作 API；第二部分是 README、架構文件或狀態紀錄列出的路徑。第二部分的詳細 schema 未能由本次提供的實作內容核對，故明確標示待確認。

## Agent 協作

下列端點定義於 `server/features/agents.py`。端點會先檢查本機來源；不符合來源政策時會呼叫拒絕處理函式。拒絕回應的精確狀態碼與本文未提供，請以 `_origin.py` 實作為準。

### `POST /api/agents/task`

執行人物研究、公司研究或會議準備任務，並將結果儲存為本機成果卡片。

**請求 JSON**

| 欄位 | 型別 | 必要 | 說明 |
|---|---|---:|---|
| `kind` | string | 是 | `research_person`、`research_company` 或 `meeting_prep`。 |
| `target` | string | 視情況 | 研究對象；去除首尾空白後最多取 120 字元。 |
| `ask` | string | 否 | 任務補充文字；最多取 1000 字元。 |
| `lang` | string | 否 | 前端可傳入的語言提示。實際繁中／英文判定由請求物件的 `req.lang_zh()` 處理。 |

若 `target` 與 `ask` 均為空，回傳 HTTP 400。`kind` 不在支援清單時回傳 HTTP 400，並附 `error` 與 `kinds`。

**成功回應 JSON**

| 欄位 | 型別 | 說明 |
|---|---|---|
| `deliverable` | object | 新建成果卡片的 metadata，欄位見下方。 |
| `text` | string | 任務結果文字。 |
| `driver` | string | 實際使用的驅動；失敗或使用本機啟發式時可為 `local`。 |
| `fallback` | boolean | 是否使用本機 fallback。 |
| `error` | string or null | 安全化後的錯誤標籤；不包含例外訊息本文。 |
| `sources` | array | 從本機快取選取的資料來源摘要。 |

`deliverable` 內含 `id`、`title`、`kind`、`target`、`lang`、`created`、`driver`、`fallback`。成果內容會寫入本機 `data/deliverables/` 的 Markdown、HTML 與 JSON 檔案。

**可能錯誤**

- HTTP 400：`{"error":"unknown kind","kinds":[...]}`。
- HTTP 400：`{"error":"target or ask required"}`。
- 本機來源檢查拒絕：回應由來源政策函式決定。
- Agent 呼叫失敗或回傳空文字：不一定是 HTTP 錯誤；通常改用本機結果，並於回應標示 fallback。`error` 只保留例外類別及可辨識的 HTTP 狀態碼。

**範例**

```http
POST /api/agents/task
Content-Type: application/json

{
  "kind": "research_person",
  "target": "<測試對象>",
  "ask": "整理本機快取可支持的近期往來重點",
  "lang": "zh-Hant"
}
```

### `POST /api/agents/mention`

解析一段文字或本機快取郵件中的 agent 提及。若找到可執行的提及，執行相應任務並建立成果卡片；不會將郵件傳送到 alias。

**請求 JSON**

| 欄位 | 型別 | 必要 | 說明 |
|---|---|---:|---|
| `text` | string | 建議 | 待解析文字。文字解析最多使用前 4000 字元。 |
| `email_id` | string | 否 | 本機快取郵件識別碼。與 `text` 同時提供時，郵件作為 thread 來源；單獨提供時，解析快取郵件的收件人、主旨及內容。 |
| `lang` | string | 否 | 語言提示；繁中／英文判定由請求物件處理。 |

提及字詞包括 `@agent`、`@research`、`@research-company`、`@prep`、`@meeting`。`@agent` 會依文字推斷任務類型；其他別名對應固定任務類型。若 thread 提及沒有指定目標，人物研究會以寄件者作為目標，其他類型以主旨作為目標。

**成功回應 JSON**

若未觸發：

```json
{
  "triggered": false,
  "via": "text",
  "hint": "no @agent mention"
}
```

`via` 可能為 `text`、`thread` 或 `email`。未觸發時也可能回傳 `hint` 為 `not addressed to the agent`。

若觸發，回應含 `triggered: true`、`via`、`mention`、`deliverable`、`text`、`driver`、`fallback`、`error` 與 `sources`。`mention` 含 `kind`、`target`、`word`、`ask`。

**可能錯誤**

- HTTP 404：指定的 `email_id` 不存在，回應 `{"error":"not found"}`。
- HTTP 400：提及類型不合法時，任務驗證會拒絕該類型。
- 本機來源檢查拒絕：回應由來源政策函式決定。
- Agent 失敗：以本機 fallback 回應，不一定是 HTTP 錯誤。

**範例：文字觸發**

```http
POST /api/agents/mention
Content-Type: application/json

{
  "text": "@research <測試對象> 整理本機資料可支持的重點",
  "lang": "zh-Hant"
}
```

**範例：thread 內提及**

```http
POST /api/agents/mention
Content-Type: application/json

{
  "text": "@prep 整理這個 thread 的會議準備重點",
  "email_id": "<本機快取郵件 ID>"
}
```

### `GET /api/agents/deliverables`

列出本機成果卡片。

**Query 參數**

| 參數 | 型別 | 說明 |
|---|---|---|
| `limit` | integer | 列表上限，限制為 1 至 200；未提供或無法解析時使用實作預設。 |

**成功回應 JSON**

```json
{
  "deliverables": [
    {
      "id": "<成果卡片 ID>",
      "title": "<標題>",
      "kind": "research_person",
      "target": "<測試對象>",
      "lang": "zh",
      "created": "<建立時間>",
      "driver": "local",
      "fallback": true
    }
  ],
  "alias": "<agent routing alias>"
}
```

`deliverables` 依建立時間由新至舊排序。損壞或無法解析的 JSON 卡片會略過。回應中的 `alias` 是路由識別資訊，不是郵件投遞功能。

**可能錯誤**

- 本機來源檢查拒絕：回應由來源政策函式決定。
- `limit` 非整數時退回實作預設，不會因此回傳參數錯誤。

**範例**

```http
GET /api/agents/deliverables?limit=20
```

### `GET /api/agents/deliverables/*`

取得指定成果卡片的原始內容。路由尾段格式為 `<id>.<format>`；省略格式時使用 Markdown。

**路徑參數**

| 參數 | 說明 |
|---|---|
| `id` | 必須符合成果卡片 ID 格式：小寫英數與連字號，首字元為小寫英數，總長度受限。 |
| `format` | `md`、`html` 或 `json`。 |

**成功回應**

回傳原始位元組內容，並依格式設定 `Content-Type`：

- `md`：`text/markdown; charset=utf-8`
- `html`：`text/html; charset=utf-8`
- `json`：`application/json; charset=utf-8`

**可能錯誤**

- HTTP 404：ID 不合法、格式不支援或成果檔案不存在，回應 `{"error":"not found"}`。
- 本機來源檢查拒絕：回應由來源政策函式決定。

**範例**

```http
GET /api/agents/deliverables/<成果卡片 ID>.md
```

## 其他已知 HTTP 路徑

下列路徑由 README、架構文件或狀態紀錄提及。其實作檔未包含在本次提供內容中，因此表格只記錄能確認的用途；未列出的參數、回應 schema、狀態碼與錯誤均待核對。

### 核心、快取與外掛

| 方法 | 路徑 | 可確認用途 | 契約狀態 |
|---|---|---|---|
| GET | `/api/health` | 健康狀態 | 詳細 schema 待核對。 |
| GET | `/api/inbox` | 本機快取收件匣 | 查詢參數與回應 schema 待核對。 |
| GET | `/api/cache` | 查看本機快取概況 | 回應 schema 待核對。 |
| POST | `/api/cache/clear` | 清除指定範圍的快取；README 提及可用 `reseed` 控制是否重載示範郵件 | 完整請求／回應 schema 待核對。 |
| GET | `/api/features` | 列出載入功能、路由及載入錯誤 | 回應 schema 待核對。 |
| GET | `/api/ui-modules` | 列出可載入 UI 模組 | 回應 schema 待核對。 |
| GET | `/ui/modules/*` | 提供 UI 模組檔案 | 路徑驗證細節待核對。 |

### Copilot、草稿與 Agent 工具 API

| 方法 | 路徑 | 可確認用途 | 契約狀態 |
|---|---|---|---|
| POST | `/api/copilot` | Copilot 摘要、待辦、草稿或對話 | README 提及 `mode`、`item_id`、`ask`、`lang`；完整 schema 待核對。 |
| GET | `/api/drafts` | 草稿列表 | 詳細 schema 待核對。 |
| POST／其他 | `/api/draft` | 草稿操作 | 方法與完整 schema 待核對。 |
| GET | `/api/v1/tools` | 列出 Agent 工具 | 回應 schema 待核對。 |
| GET | `/api/v1/context` | 取得 Agent context pack；README 提及 `lang` query | 完整 schema 待核對。 |
| POST | `/api/v1/tools/{name}` | 呼叫單一 Agent 工具 | 工具參數與錯誤格式待核對。 |
| POST | `/api/v1/agent/run` | 執行內建 Agent wrapper；README 範例提及 `ask`、`skill`、`lang` | 完整 schema 待核對。 |

### 帳號、技能、聯絡人與用量

| 方法 | 路徑 | 可確認用途 | 契約狀態 |
|---|---|---|---|
| GET | `/api/providers` | 列出帳號、信件數及上次同步結果；不回傳密碼 | 欄位與錯誤 schema 待核對。 |
| POST | `/api/providers/check` | IMAP 帳號登入與 `EXAMINE` 連線測試 | 請求／回應 schema 待核對。 |
| GET | `/api/skills` | 列出技能 | 詳細 schema 待核對。 |
| POST | `/api/skills/run` | 執行技能 | 詳細 schema 待核對。 |
| POST | `/api/skills/settings` | 更新技能開關；關閉的技能會拒絕執行 | 請求／回應 schema 待核對。 |
| GET | `/api/crm/contacts` | 取得本機 CRM 聯絡人 | 詳細 schema 待核對。 |
| POST | `/api/crm/contacts/update` | 更新本機 CRM 聯絡人 | 請求／回應 schema 待核對。 |
| POST | `/api/crm/contacts/delete` | 刪除本機 CRM 聯絡人 | 請求／回應 schema 待核對。 |
| GET | `/api/usage` | 取得 BYOK token 用量資訊 | 回應 schema 待核對。 |

### 分流、Brain、搜尋與聯絡人

| 方法 | 路徑 | 可確認用途 | 契約狀態 |
|---|---|---|---|
| GET | `/api/triage` | 分流列表 | 詳細 schema 待核對。 |
| GET | `/api/triage/item/<id>` | 單封信的分流資訊 | 詳細 schema 待核對。 |
| GET | `/api/triage/digest` | 電子報 digest | 詳細 schema 待核對。 |
| GET | `/api/triage/tasks` | 任務列表 | 詳細 schema 待核對。 |
| GET | `/api/triage/history` | 任務操作歷史 | 詳細 schema 待核對。 |
| POST | `/api/triage/summarize` | 產生摘要 | 詳細 schema 待核對。 |
| POST | `/api/triage/summaries` | 批次摘要 | 詳細 schema 待核對。 |
| POST | `/api/triage/digest` | 建立 digest | 詳細 schema 待核對。 |
| POST | `/api/triage/tasks` | 建立分流任務 | 詳細 schema 待核對。 |
| POST | `/api/triage/tasks/update` | 更新分流任務 | 詳細 schema 待核對。 |
| POST | `/api/triage/history` | 寫入／取得歷史的具體行為待核對。 |
| `/api/brain/*` | — | Email Brain profile、推論修正等功能 | 子路徑與方法未能由提供內容完整列出。 |
| `/api/search` | — | 本機搜尋 | 查詢參數與回應 schema 待核對。 |
| `/api/search/reindex` | — | 重建搜尋索引 | 方法及 schema 待核對。 |
| `/api/contacts` | — | 聯絡人搜尋或列表 | 方法及 schema 待核對。 |

### 郵件操作、撰寫、outbox、行事曆與行動端

| 方法／路徑 | 可確認用途 | 契約狀態 |
|---|---|---|
| `/api/compose/*` | 撰寫、AI Write、風格及草稿相關功能 | 子路徑與 schema 待核對。 |
| `/api/outbox/*` | 本機 outbox、人工確認、排程、取消與匯出 | 子路徑與 schema 待核對。 |
| `/api/cal/*` | 行事曆事件、feed、free/busy 與邀請草稿 | 子路徑與 schema 待核對。 |
| `/api/mark-all-read` | 將信件標為已讀 | 方法、參數與回應待核對。 |
| `/api/translate` | 郵件翻譯 | 方法、參數與回應待核對。 |
| `/api/new-since` | 新信通知輪詢 | 查詢參數與回應待核對。 |
| `/print/<id>` | 提供郵件列印版 HTML | 路徑參數及錯誤待核對。 |
| `GET /api/mobile/info` | 列出 PWA service worker 使用的快取資訊 | 詳細 schema 待核對。 |

README 另提及 `POST /api/cal/feed/delete`，請求包含 feed 的 `id`；成功及錯誤回應 schema 待核對。
