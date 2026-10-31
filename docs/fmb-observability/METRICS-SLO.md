# 指標與初始 SLO

## 1. 指標發布方式

Openinbox 維持零 pip 與本機優先，因此建議：

1. 在同一程序內維護標準 library 實作的 counter、gauge 與 histogram。
2. 每次程序啟動時載入當日聚合指標；每日結束後保存一份聚合結果。
3. 指標只透過 loopback 的本機端點或本機儀表板讀取。
4. 不主動推送至遠端 collector。
5. 未來若要對接 Prometheus、OpenTelemetry 或其他工具，必須另開任務評估資料外送與額外相依，不能在本方案中預設啟用。

## 2. 命名與標籤規則

- Counter 以 `_total` 結尾。
- Histogram 以 `_milliseconds` 或 `_bytes` 等單位結尾。
- Gauge 表示「目前值」，不表示累計量。
- 標籤只允許固定或低基數值：
  - `component`
  - `driver`
  - `method`
  - `route_template`
  - `status_class`
  - `outcome`
  - `tool_name`
  - `engine`
  - `operation`
  - `job_name`
  - `reason_code`
- 不使用 request ID、trace ID、郵件 ID 或任意 correlation ID 作為 metric label。
- 原始 status code 可放在事件；聚合指標使用 `2xx`、`3xx`、`4xx`、`5xx` 等低基數類別。
- `account_ref` 僅可用於帳號狀態 gauge；不得用於高流量 request counter。若未來需要遠端匯出，應先移除此維度。

## 3. 建議指標

### 3.1 HTTP 與 MCP

| 指標 | 類型 | 建議標籤 | 意義 |
|---|---|---|---|
| `http_requests_total` | counter | `route_template`、`http_method`、`status_class` | HTTP 請求總數 |
| `http_request_duration_milliseconds` | histogram | `route_template`、`http_method` | HTTP 延遲分布 |
| `http_requests_in_flight` | gauge | 無 | 進行中 HTTP 請求數 |
| `http_response_bytes_total` | counter | `route_template`、`status_class` | 回應大小總量，不含內容 |
| `http_origin_rejections_total` | counter | `route_template`、`reason_code` | local-origin 拒絕數 |
| `mcp_requests_total` | counter | `method`、`tool_name`、`outcome` | MCP 請求總數 |
| `mcp_request_duration_milliseconds` | histogram | `method`、`tool_name` | MCP 延遲分布 |
| `mcp_tool_errors_total` | counter | `tool_name`、`reason_code` | MCP 工具錯誤數 |

### 3.2 郵件同步與供應商

| 指標 | 類型 | 建議標籤 | 意義 |
|---|---|---|---|
| `mail_sync_attempts_total` | counter | `driver`、`outcome` | 同步嘗試總數 |
| `mail_sync_duration_milliseconds` | histogram | `driver`、`outcome` | 單一帳號同步延遲 |
| `mail_sync_messages_total` | counter | `driver`、`result_kind` | 收到、寫入與更新的數量 |
| `mail_sync_accounts_failed_total` | counter | `driver`、`reason_code` | 失敗的帳號同步次數 |
| `mail_account_last_success_age_seconds` | gauge | `account_ref`、`driver` | 距上次成功同步的時間 |
| `provider_probe_attempts_total` | counter | `driver`、`outcome` | 唯讀連線探測總數 |
| `provider_probe_duration_milliseconds` | histogram | `driver`、`outcome` | 探測延遲 |
| `imap_readonly_violations_total` | counter | `command_name` | 唯讀安全不變量破壞數 |

### 3.3 Agent 與模型用量

| 指標 | 類型 | 建議標籤 | 意義 |
|---|---|---|---|
| `agent_tasks_total` | counter | `driver`、`operation`、`outcome` | Agent 任務總數 |
| `agent_task_duration_milliseconds` | histogram | `driver`、`operation`、`outcome` | Agent 任務延遲 |
| `agent_fallback_total` | counter | `requested_driver`、`reason_code` | fallback 總數 |
| `agent_driver_errors_total` | counter | `driver`、`operation`、`reason_code` | driver 錯誤總數 |
| `agent_input_tokens_total` | counter | `driver`、`estimated` | 輸入 token 數量 |
| `agent_output_tokens_total` | counter | `driver`、`estimated` | 輸出 token 數量 |

用量 token 是允許的數值欄位；禁止的是任何 token、session 或 credential 值。

### 3.4 搜尋、索引與 SQLite

| 指標 | 類型 | 建議標籤 | 意義 |
|---|---|---|---|
| `search_requests_total` | counter | `engine`、`outcome` | 搜尋請求總數 |
| `search_duration_milliseconds` | histogram | `engine`、`outcome` | 搜尋延遲 |
| `search_result_count` | histogram | `engine` | 結果數分布，不記錄結果內容 |
| `search_index_documents` | gauge | `engine` | 目前索引文件數 |
| `search_index_last_success_age_seconds` | gauge | `engine` | 距上次索引成功的時間 |
| `search_index_rebuilds_total` | counter | `engine`、`outcome` | 索引重建總數 |
| `db_operations_total` | counter | `operation`、`outcome` | 資料庫操作總數 |
| `db_operation_duration_milliseconds` | histogram | `operation`、`outcome` | 資料庫操作延遲 |
| `db_busy_total` | counter | `operation` | SQLite busy／lock 次數 |
| `db_integrity_checks_total` | counter | `outcome` | 完整性檢查總數 |

### 3.5 工作流、背景工作與觀測系統

| 指標 | 類型 | 建議標籤 | 意義 |
|---|---|---|---|
| `outbox_transitions_total` | counter | `from_state`、`to_state`、`reason_code` | 本機 outbox 狀態轉移 |
| `outbox_due_lag_seconds` | histogram | 無 | 到期項目被處理的延遲 |
| `rule_apply_total` | counter | `outcome` | 規則套用總數 |
| `rule_dry_run_total` | counter | `outcome` | 規則預覽總數 |
| `calendar_feed_imports_total` | counter | `outcome` | ICS feed 匯入總數 |
| `background_jobs_total` | counter | `job_name`、`outcome` | 背景工作總數 |
| `background_job_duration_milliseconds` | histogram | `job_name`、`outcome` | 背景工作延遲 |
| `feature_load_failures_total` | counter | `feature_name`、`required` | 功能載入失敗數 |
| `observability_events_total` | counter | `event_name`、`severity` | 已輸出事件數 |
| `observability_events_dropped_total` | counter | `sink_type` | 因 queue 或容量而遺失的事件數 |
| `observability_sink_failures_total` | counter | `sink_type` | 觀測寫入失敗數 |
| `privacy_policy_violations_total` | counter | `policy_rule_id`、`sink_type` | 敏感資料規則命中數 |
| `process_uptime_seconds` | gauge | 無 | 程序運行時間 |
| `process_start_time_seconds` | gauge | 無 | 程序啟動時間 |
| `disk_free_bytes` | gauge | `volume_class` | repo 所在磁碟可用空間，不記錄 mount path |

## 4. 建議 histogram buckets

| 類型 | 建議 bucket（毫秒） |
|---|---|
| 本機快取 API | `5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000` |
| MCP | `10, 25, 50, 100, 250, 500, 1000, 2500` |
| Agent／外部 driver | `100, 250, 500, 1000, 2500, 5000, 10000, 30000, 60000, 120000` |
| 郵件同步／索引 | `100, 250, 500, 1000, 2500, 5000, 10000, 30000, 60000, 300000` |

搜尋結果數可使用 `0, 1, 5, 10, 50, 100, 500, 1000+`；這只用於容量趨勢，不顯示實際搜尋內容。

## 5. 初始 SLO

### 5.1 衡量期間與基本規則

- 初始期間採 28 天 rolling window，並以 5 分鐘 bucket 計算。
- 程式停止、維護或本機電腦休眠期間不計入可用率；恢復後應有短暫暖機期。
- 客戶輸入錯誤、明確停用功能與預期的 4xx 不計入服務可用率，但仍可另外統計。
- local-origin 拒絕屬安全事件，不應被當成服務可用率下降。
- demo 模式不納入 live 供應商同步、外部 Agent 或正式資料 SLO。
- 外部供應商故障需分成「本機內部錯誤」與「外部相依失敗」，避免錯誤歸責；兩者都必須可見。

### 5.2 SLO 表

| ID | SLI 與公式 | 初始目標 | 資料來源 | 備註 |
|---|---|---:|---|---|
| `OBJ-API-AVAIL` | 合格 HTTP 請求中 status `<500` 的比例 | 99.5%／28 天 | `http_requests_total` | 合格請求只包含已註冊且通過輸入驗證的路由 |
| `OBJ-MCP-AVAIL` | 合格 MCP request 中無協定或工具錯誤的比例 | 99.5%／28 天 | `mcp_requests_total` | 工具找不到或 client 取消不算服務錯誤 |
| `OBJ-SYNC-EXEC` | 合格同步嘗試中，沒有本機內部錯誤的比例 | 99.0%／28 天 | `mail_sync_attempts_total` | 設定錯誤與使用者憑證失效另列，不掩蓋 |
| `OBJ-SYNC-FRESH` | 同步嘗試在 15 分鐘內完成的比例 | 95%／28 天 | 同步事件與耗時 | 只計預期執行中的週期 |
| `OBJ-CACHE-LATENCY` | 本機快取 API 的 p95 延遲 | ≤500 ms | `http_request_duration_milliseconds` | 排除同步、Agent、索引重建與外部 driver |
| `OBJ-MCP-LATENCY` | 本機 MCP 操作的 p95 延遲 | ≤1,000 ms | `mcp_request_duration_milliseconds` | 排除外部 Agent 執行時間時需分開呈現 |
| `OBJ-SEARCH` | 合格搜尋請求中成功完成的比例 | 99.0%／28 天 | `search_requests_total` | LIKE fallback 本身不算失敗，但需顯示 engine |
| `OBJ-INDEX-FRESH` | 已變更郵件在 5 分鐘內可被搜尋的比例 | 99.0%／28 天 | 索引事件與測試探針 | 不記錄被搜尋郵件內容 |
| `OBJ-AGENT-LATENCY` | 外部 Agent 任務在 60 秒內完成且未 fallback 的比例 | 95%／28 天 | `agent_tasks_total`、延遲 histogram | 不含 `local` driver 與輸入驗證失敗 |
| `OBJ-AGENT-FALLBACK` | 外部 Agent 任務使用 fallback 的比例 | ≤10%／28 天 | `agent_fallback_total` | 沒有設定外部 driver 時不計入 |
| `OBJ-FEATURE-LOAD` | 必要功能模組成功載入的比例 | 100%／每次啟動 | 功能事件 | 可選功能失敗標為 degraded |
| `OBJ-DB-INTEGRITY` | 完整性檢查通過的比例 | 100%／每次檢查 | DB 事件 | 失敗零容忍 |
| `OBJ-LOG-SAFETY` | 觀測輸出中含禁止欄位或值的事件數 | 0 | 隱私掃描器 | 資料安全 SLO，零容忍 |
| `OBJ-READONLY-MAIL` | IMAP 工作階段出現遠端寫入命令的數量 | 0 | `imap_readonly.violation` | 唯讀安全 SLO，零容忍 |
| `OBJ-OUTBOX-SAFETY` | 未經明確確認即進入可寄出狀態的項目數 | 0 | `outbox.transition` | 目前沒有預設對外寄送路徑 |
| `OBJ-OBS-DURABILITY` | 已接受事件成功落地或被明確計數為 dropped 的比例 | 99.9%／28 天 | sink 與 drop 指標 | dropped 不等於資料內容遺失，但必須可見 |

## 6. 公式與排除條件

### 6.1 HTTP 可用率

```text
good_http = 合格 HTTP requests - status >= 500 的合格 HTTP requests
availability = good_http / 合格 HTTP requests
```

排除：

- 路由不存在、方法不允許與 client 輸入錯誤。
- 使用者主動取消。
- 明示停用的功能。
- local-origin 安全拒絕；另由安全告警計算。

### 6.2 同步成功率

```text
good_sync = 沒有本機內部錯誤的合格同步嘗試
sync_success = good_sync / 合格同步嘗試
```

分開顯示但仍提供健康告警：

- 憑證參照不存在。
- 上游拒絕認證。
- TLS、DNS、連線逾時。
- 上游限流或服務不可用。

這些分類可使用固定 `reason_code`，但不得帶入上游回應本文。

### 6.3 Agent fallback 率

```text
fallback_rate = fallback external agent tasks / eligible external agent tasks
```

排除：

- `local` driver。
- 輸入驗證失敗。
- 使用者取消。
- 沒有設定外部 driver 的本機操作。

### 6.4 索引新鮮度

以不含業務內容的本機測試探針定期寫入暫存測試文件，再確認可在索引中找到。正式資料不需為了量測而被搜尋或記錄。

## 7. 錯誤預算與 burn rate

`OBJ-API-AVAIL` 為 99.5% 時，28 天錯誤預算約為 0.5%，即約 216 分鐘。

| 類型 | 條件 | 用途 |
|---|---|---|
| 快速消耗 | 錯誤率為預算速率的 14.4 倍，維持 1 小時 | 立即處理 |
| 中速消耗 | 錯誤率為預算速率的 6 倍，維持 6 小時 | 優先處理 |
| 慢速消耗 | 錯誤率為預算速率的 3 倍，維持 3 天 | 工作項修正 |

本機單使用者流量可能不足以計算穩定比率。因此：

- 比率告警必須設最小樣本數。
- 低流量時改用「連續失敗次數」與「距上次成功時間」。
- 不因只有一次預期中的外部認證失敗就判定服務中斷。

## 8. 初始目標的性質

以上 SLO 是保守起點，不是已達成結果。實際門檻應在累積至少 28 天本機資料後，由 BOB 依使用頻率、供應商特性與可接受中斷時間調整。資料安全、唯讀郵件與 outbox 確認三項維持零容忍，不建議放寬。
