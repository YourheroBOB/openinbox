# 關鍵事件與欄位契約

## 1. 命名與傳輸原則

- 事件名稱使用小寫 snake case，格式為 `domain.action`，例如 `mail.sync.completed`。
- 每個事件是一列 UTF-8 JSON Lines；不得把巢狀任意物件直接序列化。
- `timestamp` 一律使用 RFC 3339 UTC；耗時使用 monotonic clock 計算的 `duration_ms`。
- 事件必須在操作完成、拒絕或失敗時發出；不要用「開始」事件代替完成事件。
- 所有欄位先通過 schema 驗證與允許清單；未知欄位直接丟棄，不原樣保存。
- 同一操作不應同時產生兩個重複錯誤事件；HTTP 完成事件已含 status，元件失敗事件只描述元件層原因。
- 成功事件可只記必要摘要；錯誤事件不得加入原始錯誤本文。

## 2. 通用欄位

| 欄位 | 型別 | 必要性 | 說明 |
|---|---|---|---|
| `schema_version` | integer | 必填 | 目前固定為 `1`；欄位語意破壞時升版 |
| `timestamp` | string | 必填 | UTC RFC 3339，例如毫秒精度 |
| `event_name` | string | 必填 | 固定事件名稱 |
| `severity` | enum | 必填 | `debug`、`info`、`warn`、`error`、`critical` |
| `source` | enum | 必填 | `http`、`mcp`、`background`、`cli`、`internal` |
| `component` | string | 必填 | 程式碼內固定元件名，不使用動態使用者名稱 |
| `outcome` | enum | 必填 | `success`、`failure`、`fallback`、`degraded`、`skipped`、`denied` |
| `operation_id` | string | 條件必填 | 背景工作、同步或非同步作業的 opaque ID |
| `request_id` | string | HTTP/MCP 必填 | 每個外部請求的 opaque ID |
| `trace_id` | string | 關聯操作必填 | 將同一使用者旅程串起來的 opaque ID |
| `duration_ms` | integer | 完成事件必填 | 非負整數，不使用系統時間相減 |
| `driver` | enum | 條件必填 | `demo`、`local`、`imap`、`gog`、`gsk`、`openai_compatible`、`cli`、`http` 等受控值 |
| `account_ref` | string | 條件必填 | 隨機產生、不由信箱或名稱衍生的本機帳號代號 |
| `route_template` | string | HTTP 必填 | 已註冊的靜態路由模板，不含實際 path 參數 |
| `http_method` | enum | HTTP 必填 | `GET`、`POST` 等 |
| `http_status_code` | integer | HTTP 必填 | 實際 HTTP status |
| `result` | object | 條件必填 | 只允許核准的計數或布林值 |
| `error` | object | 失敗必填 | 只允許安全錯誤欄位，詳見第 4 節 |

### 2.1 `outcome` 定義

| 值 | 意義 |
|---|---|
| `success` | 操作完成且符合預期 |
| `failure` | 操作未完成 |
| `fallback` | 外部或主要 driver 失敗，改用本機替代路徑且仍完成操作 |
| `degraded` | 操作完成，但部分能力降低或資料不完整 |
| `skipped` | 因明確條件未執行，例如功能已停用 |
| `denied` | 因安全或權限條件被拒絕 |

### 2.2 `severity` 定義

| 等級 | 定義 |
|---|---|
| `debug` | 本機診斷細節；不得預設在高流量路徑大量產生 |
| `info` | 正常生命週期與成功事件 |
| `warn` | 可恢復的降級、fallback、缺少可選設定或接近門檻 |
| `error` | 單次操作失敗且需要處置 |
| `critical` | 資料安全、完整性、唯讀安全或未授權狀態轉移遭破壞 |

## 3. Correlation 與 ID 規則

1. `request_id` 每個 HTTP 或 MCP request 重新產生，使用隨機 UUID 或同等不可猜測值。
2. `trace_id` 在一個高階操作開始時產生；同步、搜尋索引更新、Agent fallback 等子操作沿用。
3. `operation_id` 用於沒有外部 request 的背景工作；例如一次完整同步或索引重建。
4. 不使用下列資料作為 correlation ID：
   - 郵件 ID、thread ID、message ID。
   - 草稿 ID、outbox ID 或確認 token。
   - 成果卡片 ID 或檔名；現有成果 ID 可能由對象 slug 產生。
   - 行事曆 UID、聯絡人 ID、搜尋詞或使用者輸入。
5. correlation ID 只用於本機關聯，不得視為匿名化資料；若外部系統未來接收，須另行評估。

## 4. 安全錯誤模型

```json
{
  "code": "TIMEOUT",
  "type": "TimeoutError",
  "http_status": 504,
  "retryable": true
}
```

允許欄位：

| 欄位 | 說明 |
|---|---|
| `code` | 穩定且正規化的錯誤碼，不使用動態文字 |
| `type` | 例外類別或元件定義的短類別名；不包含訊息 |
| `http_status` | 適用時的 HTTP status |
| `retryable` | 該錯誤是否值得重試 |
| `origin` | `local`、`upstream`、`provider`、`agent`、`database` 等固定值 |

禁止欄位：

- `error.message`
- `error.detail`
- `error.stack`
- `error.response`
- `error.body`
- `error.stderr`
- `error.stdout`
- `error.headers`
- `error.request`
- 任何包含上游原文或使用者內容的欄位

## 5. 事件目錄

以下事件是建議契約；目前程式尚未全面產出。

### 5.1 服務生命週期與設定

| 事件 | 觸發時機 | 專用欄位 | 預設 severity |
|---|---|---|---|
| `service.started` | 服務程序啟動 | `app_version`、`mode`、`feature_count` | info |
| `service.ready` | 資料庫、功能模組與路由已可服務 | `feature_count`、`failed_feature_count`、`startup_duration_ms` | info |
| `service.stopping` | 正常或訊號停止 | `reason`（固定 enum）、`uptime_seconds` | info |
| `feature.load.failed` | 可選或必要功能匯入失敗 | `feature_name`、`error` | error；必要功能為 critical |
| `config.validation.failed` | 設定結構或安全規則驗證失敗 | `config_name`（固定名稱）、`error` | error |
| `credential.reference.missing` | 設定引用的憑證不存在 | `config_name`、`driver`、`error.code` | warn |
| `db.integrity.check.completed` | 啟動或排程完整性檢查 | `duration_ms`、`result.check_count` | info；失敗為 critical |

`mode` 只允許 `demo` 或 `live`。`feature_name` 必須來自 repo 內固定程式碼，不可由設定動態產生。

### 5.2 HTTP 與請求安全

| 事件 | 觸發時機 | 專用欄位 | 預設 severity |
|---|---|---|---|
| `http.request.completed` | 每個 HTTP request 結束 | `route_template`、`http_method`、`http_status_code`、`duration_ms`、`result.response_bytes` | info；5xx 為 error |
| `http.request.rejected` | local-origin 或其他安全條件拒絕 | `route_template`、`http_method`、`http_status_code`、`error` | warn；異常大量時升級 |
| `http.request.timeout` | 請求處理逾時 | `route_template`、`http_method`、`duration_ms`、`error` | error |
| `http.response.truncated` | 僅指觀測輸出被截斷，不指業務 body | `route_template`、`result.original_bytes`、`result.stored_bytes` | warn |

`http.request.completed` 不包含 query string、原始 path、header、request body 或 response body。`result.response_bytes` 只能是整數位元組數。

### 5.3 郵件同步與供應商探測

| 事件 | 觸發時機 | 專用欄位 | 預設 severity |
|---|---|---|---|
| `mail.sync.started` | 單一帳號同步開始 | `account_ref`、`driver`、`trigger` | debug |
| `mail.sync.completed` | 單一帳號同步成功 | `account_ref`、`driver`、`duration_ms`、計數欄位 | info |
| `mail.sync.failed` | 單一帳號同步失敗 | `account_ref`、`driver`、`duration_ms`、`error` | error |
| `mail.sync.batch.completed` | 全帳號同步批次結束 | `duration_ms`、總計數、成功／失敗數 | info；部分失敗為 warn |
| `provider.probe.completed` | 唯讀連線探測成功 | `account_ref`、`driver`、`duration_ms` | info |
| `provider.probe.failed` | 唯讀連線探測失敗 | `account_ref`、`driver`、`duration_ms`、`error` | warn |
| `imap.readonly.violation` | 偵測到非允許的遠端寫入命令 | `command_name`（固定 enum）、`account_ref` | critical |

同步計數只允許：

- `result.received_count`
- `result.inserted_count`
- `result.updated_count`
- `result.unchanged_count`
- `result.unread_count`
- `result.account_count`
- `result.success_count`
- `result.failure_count`

不得記錄主旨、寄件人、收件人、mailbox 名稱、message ID、thread ID 或郵件片段。`imap.readonly.violation.command_name` 只允許 `SELECT`、`STORE`、`EXPUNGE`、`MOVE`、`COPY`、`DELETE` 等固定命令類別，不帶參數。

### 5.4 Agent 與用量

| 事件 | 觸發時機 | 專用欄位 | 預設 severity |
|---|---|---|---|
| `agent.task.started` | Agent 任務開始 | `driver`、`operation`、`trace_id` | debug |
| `agent.task.completed` | 任務成功完成 | `driver`、`operation`、`duration_ms`、安全計數 | info |
| `agent.task.fallback` | 改用本機替代路徑 | `requested_driver`、`fallback_driver`、`reason_code`、`duration_ms` | warn |
| `agent.driver.failed` | 外部 driver 失敗 | `driver`、`operation`、`duration_ms`、`error` | error |
| `agent.usage.recorded` | 記錄模型用量 | `driver`、`result.input_tokens`、`result.output_tokens`、`result.estimated` | info |

`operation` 只允許固定值，例如 `research_person`、`research_company`、`meeting_prep`、`summarize`、`rewrite_query`、`generate_draft`。

禁止記錄：

- 對象、人物或公司名稱。
- 任務 ask、提示詞、context pack、persona、來源信件或片段。
- 模型回答、摘要、草稿、HTML、Markdown 或研究結果。
- 原始 token 字串；只允許 token 數量。

### 5.5 MCP

| 事件 | 觸發時機 | 專用欄位 | 預設 severity |
|---|---|---|---|
| `mcp.request.completed` | JSON-RPC request 完成 | `method`、`tool_name`、`duration_ms`、`outcome` | info |
| `mcp.request.failed` | JSON-RPC request 失敗 | `method`、`tool_name`、`duration_ms`、`error` | error |
| `mcp.tool.failed` | 工具執行失敗 | `tool_name`、`duration_ms`、`error` | error |

`method` 只允許 `initialize`、`tools/list`、`tools/call`、`ping`。`tool_name` 只能來自 MCP 固定工具清單。不得記錄 `params`、`arguments`、`result` 或工具輸出。

### 5.6 搜尋、索引、快取與資料庫

| 事件 | 觸發時機 | 專用欄位 | 預設 severity |
|---|---|---|---|
| `search.request.completed` | 搜尋完成 | `engine`、`duration_ms`、`result.result_count`、`result.query_length_bucket` | info |
| `search.request.failed` | 搜尋失敗 | `engine`、`duration_ms`、`error` | error |
| `search.index.rebuild.started` | 索引重建開始 | `engine`、`operation_id` | debug |
| `search.index.rebuild.completed` | 索引重建完成 | `engine`、`duration_ms`、文件計數 | info |
| `search.index.rebuild.failed` | 索引重建失敗 | `engine`、`duration_ms`、`error` | error |
| `cache.clear.completed` | 本機快取清除完成 | `duration_ms`、各類清除／保留計數 | info |
| `db.operation.failed` | SQLite 操作失敗 | `operation`（固定 enum）、`duration_ms`、`error` | error |

`query_length_bucket` 只允許 `0`、`1-10`、`11-100`、`101-1000`、`1001+`。不得記錄搜尋詞或解析後運算式。

### 5.7 自動化、Outbox、行事曆與背景工作

| 事件 | 觸發時機 | 專用欄位 | 預設 severity |
|---|---|---|---|
| `rule.dry_run.completed` | 規則預覽完成 | `duration_ms`、`result.rule_count`、`result.match_count` | info |
| `rule.apply.completed` | 規則套用完成 | `duration_ms`、動作類型計數 | info |
| `rule.apply.failed` | 規則套用失敗 | `duration_ms`、`error` | error |
| `outbox.transition` | 本機 outbox 狀態轉移 | `from_state`、`to_state`、`reason_code`、`duration_ms` | info；未授權轉移為 critical |
| `calendar.feed.import.completed` | ICS feed 匯入完成 | `source_ref`、`duration_ms`、事件計數 | info |
| `calendar.feed.import.failed` | ICS feed 匯入失敗 | `source_ref`、`duration_ms`、`error` | error |
| `background.job.started` | 背景工作開始 | `job_name`、`operation_id` | debug |
| `background.job.completed` | 背景工作完成 | `job_name`、`duration_ms`、安全計數 | info |
| `background.job.failed` | 背景工作失敗 | `job_name`、`duration_ms`、`error` | error |

`source_ref` 必須是隨機 opaque ID，不得使用 ICS URL、檔名、mailbox 名稱、事件 UID 或主辦人。`job_name` 只能來自固定清單，例如 `outbox_due_scan`、`search_index_update`、`overnight_run`。

### 5.8 觀測系統自身與資料安全

| 事件 | 觸發時機 | 專用欄位 | 預設 severity |
|---|---|---|---|
| `privacy.policy.violation.detected` | 欄位允許清單或內容掃描器發現禁止資料 | `policy_rule_id`、`sink_type`、`result.count` | critical |
| `observability.sink.failed` | 本機事件或指標寫入失敗 | `sink_type`、`error` | error |
| `observability.events.dropped` | 非同步 queue 滿而丟棄事件 | `sink_type`、`result.dropped_count` | error |

禁止把命中值、原始欄位值、原始事件或 offender 欄位名稱寫入違規事件本身；只記錄固定 policy rule ID 與計數。

## 6. 建議事件範例

以下只包含固定 schema 與假 metadata，不含任何業務內容：

```json
{
  "schema_version": 1,
  "timestamp": "2026-01-01T00:00:00.000Z",
  "event_name": "mail.sync.completed",
  "severity": "info",
  "source": "background",
  "component": "mail_sync",
  "outcome": "success",
  "operation_id": "op_fake_for_docs",
  "trace_id": "trace_fake_for_docs",
  "duration_ms": 12,
  "driver": "imap",
  "account_ref": "account_fake_for_docs",
  "result": {
    "received_count": 3,
    "stored_count": 3
  }
}
```

## 7. 發送規則

1. 事件 schema 驗證失敗時，不允許將未知欄位補進事件；改記 `observability.sink.failed`。
2. `result` 與 `error` 必須使用固定欄位集合；任意 `dict` 不得直接落盤。
3. 事件中的時間、ID 與固定 enum 不得由使用者文字組合。
4. 背景工作與外部 driver 逾時必須保留 `operation_id`，方便同一作業的 start/completion 對照。
5. 敏感資料掃描應在 emitter 前執行；掃描失敗時丟棄該事件並產生不含內容的違規計數。
6. 初期以完整記錄為主；只有在本機磁碟壓力證實有需要時，才對高成功率的 `debug` 事件做明確且可觀測的抽樣。
