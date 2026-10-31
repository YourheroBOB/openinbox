# 現況盤點：日誌、指標與錯誤回報

## 1. 盤點基準與限制

本盤點以提供的 Openinbox 預設分支內容為基準，採靜態方式檢視程式、架構文件、狀態檔、README 與測試說明。

- 未連線任何正式服務或正式郵件系統。
- 未執行 live 模式、IMAP、Agent、MCP 客戶端或外部供應商。
- 本文中的「未發現」表示在本次可檢視內容中未看到對應機制，不等同於斷言所有可能執行環境都絕對不存在。
- 為避免誤觸真實資料，本文不列出任何實際郵件地址、姓名、案件、LINE 訊息或憑證值。

## 2. 現有可觀測訊號總表

| 領域 | 現有訊號 | 目前用途 | 限制與缺口 |
|---|---|---|---|
| 程序健康 | `GET /api/health` | 讓本機操作者確認服務可回應 | 未見統一 readiness、啟動耗時、版本與元件健康模型；不能直接算出歷史可用率 |
| HTTP 回應 | 各 API 的 JSON 回應與 HTTP status | 表示單次操作成功或失敗 | 錯誤格式未統一；未見 request ID、route template、耗時或跨請求關聯 |
| 功能載入 | `GET /api/features` 與 UI loader | 顯示已載入功能、路由及匯入錯誤 | 僅為啟動時狀態；未形成事件、時間序列或告警 |
| 帳號同步 | `LAST_SYNC`、`GET /api/providers`、各帳號未讀數與上次同步結果 | 顯示帳號最近同步成功或失敗 | 僅保存「最近一次」狀態；缺少每次嘗試、耗時分布、失敗率與 stale 歷史 |
| 供應商連線測試 | `POST /api/providers/check` | 對 IMAP 做登入與唯讀 mailbox 檢查 | 沒有測試耗時、分類錯誤率或歷史；診斷與完整同步尚未分離成獨立 SLI |
| Agent 執行 | API 回應中的 `driver`、`fallback` 與錯誤欄位 | 顯示使用本機、外部或 fallback 結果 | 未見全域 request rate、fallback rate、driver 延遲或 token 使用率聚合 |
| Agent 錯誤 | `server/features/agents.py` 的 `error_label()` | 只保留例外類型及可辨識的 HTTP status，不回傳原始訊息 | 是目前較明確的安全基線，但尚未統一套用到所有元件 |
| BYOK 用量 | `data/usage.jsonl` 與 `GET /api/usage` | 記錄輸入／輸出 token 數及是否為估算值 | 是用量帳本，不是完整操作指標；沒有失敗率、延遲或 fallback 關聯 |
| 搜尋索引 | `GET /api/search/status`、搜尋回應中的 engine | 顯示 FTS5 或 LIKE、索引狀態 | 未見索引最後成功時間、增量更新耗時、文件數時序或 stale SLO |
| 快取 | `GET /api/cache`、`POST /api/cache/clear` | 顯示與清除本機快取 | 缺少各類快取大小、命中率、清除耗時與衍生資料一致性指標 |
| Outbox | SQLite 的 outbox 狀態、log 與設定 | 支援本機排程、倒數撤銷、確認與取消 | 屬業務稽核資料；缺少狀態轉移錯誤率、到期處理延遲與安全不變量告警 |
| 分流任務 | `triage_tasks`、`triage_history` | 保存任務與操作歷史 | 屬產品功能資料，不應直接視為操作日誌 |
| Agent 回合／成果 | `agent_turns`、`data/deliverables/` | 保存摘要或研究成果供產品使用 | 內容可能含郵件片段，不可直接當觀測 log 匯出 |
| MCP | JSON-RPC initialize、tools/list、tools/call、ping 的協定回應 | 讓客戶端判斷成功與失敗 | 未見 MCP 專屬 request ID、工具呼叫率、延遲或錯誤分類聚合 |
| 請求來源保護 | `_origin.py` 的 local-origin 檢查與拒絕回應 | 降低跨來源修改請求風險 | 未見拒絕率告警或安全事件結構化紀錄 |
| 背景工作 | outbox 到期處理、overnight、索引更新等程序內工作 | 完成產品工作 | 未見統一的 job start/completion/failure 事件與逾時告警 |
| 標準輸出／錯誤輸出 | 程序 stdout/stderr 與未捕捉例外 | 供啟動者或服務管理器查看 | 未見中央 JSON formatter、欄位允許清單、rotation、retention 或 correlation ID |
| 測試與 smoke | `unittest`、`scripts/smoke.sh`、CI workflow | 驗證程式可建置、可啟動且主要流程可用 | 屬部署前驗證訊號，不能取代執行期 SLO 與告警 |

## 3. 現有「日誌」與資料表盤點

### 3.1 可視為日誌或時間序列的資料

| 資料 | 性質 | 可觀測價值 | 不可直接視為通用日誌的原因 |
|---|---|---|---|
| `data/usage.jsonl` | 每次模型呼叫的 token 用量列 | 模型成本、呼叫量、估算比例 | 沒有事件名稱、request ID、錯誤碼、耗時或 fallback 欄位；內容刻意不含提示與回答 |
| outbox log | 本機狀態轉移與排程紀錄 | 排程、確認、取消與到期流程 | 是業務稽核；不涵蓋 HTTP、同步與背景工作的系統狀態 |
| triage history | 使用者對分流任務的操作歷史 | 產品流程追蹤 | 資料量與用途受產品功能驅動，不能代表服務健康 |
| provider `LAST_SYNC` | 每帳號最近一次同步狀態 | 顯示帳號目前是否健康 | 是點狀態，不是每次嘗試的時間序列 |

### 3.2 明確不是觀測日誌的資料

- `vault/` 內的人格、索引與卡片。
- `data/deliverables/` 內的 Markdown、HTML 與 JSON 成果。
- `agent_turns` 中的摘要或 Agent 結果。
- 郵件、附件、草稿、聯絡人、行事曆與搜尋索引內容。
- `accounts.json`、`agent.json`、規則或其他本機設定內容。

這些資料可能含有郵件片段、姓名、信箱、事件參與者、CRM 筆記或其他敏感資訊，不得直接串接至事件、指標、告警或儀表板。

## 4. 現有指標盤點

目前可從 API 或本機資料取得的是「單點狀態」，尚不是可支援 SLO 的時間序列：

1. 服務健康布林值。
2. 各帳號未讀數與最近同步結果。
3. 模型輸入／輸出 token 數與估算旗標。
4. 搜尋引擎是 FTS5 或 LIKE。
5. 快取內容摘要。
6. Outbox、分流任務與產品狀態數量。
7. 功能模組是否成功載入。

缺少的跨功能指標包括：

- HTTP、MCP 與背景工作的請求率、錯誤率及延遲分布。
- 每個供應商 driver 的同步成功率、耗時、延遲與每次嘗試結果。
- Agent 的 fallback 率、driver 錯誤率、逾時率與 token 使用率。
- SQLite busy／lock、交易延遲、完整性檢查與寫入失敗。
- 搜尋索引的文件數、最後成功時間與 stale 時間。
- Outbox 到期處理延遲與未授權狀態轉移。
- 觀測事件遺失率與本機檔案寫入失敗。
- 敏感欄位偵測結果。

## 5. 現有錯誤回報盤點

### 5.1 已有的正面做法

- `server/features/agents.py` 明確將外部 Agent 失敗轉為例外類型與 HTTP status，避免把 endpoint body、CLI stderr 或提示詞回傳給使用者。
- 供應商流程已有「缺少憑證參照」「登入失敗」「同步失敗」等概念，並且密碼值不應回傳。
- 使用量紀錄不保存提示詞、回答或金鑰。
- 功能模組錯誤會集中顯示在 `/api/features`，可作為啟動診斷來源。
- IMAP 流程在設計上使用 `EXAMINE` 與 `BODY.PEEK`，可建立「不得出現遠端寫入命令」的可觀測安全不變量。

### 5.2 主要不一致與風險

| 風險 | 說明 | 建議 |
|---|---|---|
| 錯誤 envelope 不一致 | 不同路由可能使用 `{error: ...}`、HTTP status 或其他欄位 | 統一穩定 `error.code`，原始文字只留在本機 UI 的安全說明層且必須先正規化 |
| 原始錯誤文字可能夾帶資料 | 例外訊息、CLI stderr、上游 body 可能包含路徑、郵件片段或憑證 | 禁止記錄 `str(exc)` 與 raw response，只記錄白名單欄位 |
| 缺 request correlation | 無法從一次 UI 錯誤追到同步、Agent 或背景工作 | HTTP、MCP、背景工作均產生 opaque `request_id`／`operation_id` |
| 缺時間序列 | 供應商只留最近一次狀態，無法計算失敗率 | 每次同步與探測都產生無內容事件及聚合指標 |
| 動態 ID 未必安全 | 郵件、thread、成果或事件 ID 可能包含信箱、對象或本機來源資訊 | correlation ID 必須重新產生，不可重用業務 ID |
| 路由可能夾帶識別碼 | 原始 path 參數可能包含郵件、成果或草稿 ID | 指標與日誌只記錄已註冊的 route template |
| 匯入錯誤可能含絕對路徑 | Python import error 常包含檔案系統路徑 | 對外只顯示元件名與穩定碼，絕對路徑不得進事件 |
| 沒有留存政策 | 目前看不到一般應用日誌的 rotation 或 retention | 未來實作設定每日檔案、大小上限與固定保留天數 |

## 6. 優先改善順序

### P0：先建立安全且可關聯的觀測骨架

1. 定義事件 schema 與欄位允許清單。
2. 統一錯誤碼與安全例外摘要。
3. 加入每次請求／操作的 opaque correlation ID。
4. 禁止任意 `message`、`context`、request/response body 與原始例外文字。

### P1：覆蓋最重要的使用者旅程

1. 供應商同步與連線探測。
2. Agent 與 MCP。
3. SQLite 與搜尋索引。
4. Outbox、規則與背景工作的狀態轉移。

### P2：建立量化管理能力

1. 本機時間序列與聚合指標。
2. 初始 SLO 與錯誤預算。
3. 本機告警與儀表板。
4. 經實際使用後調整門檻。

## 7. 現況結論

Openinbox 已有多個可用的診斷端點、安全的 Agent 錯誤摘要、供應商狀態、用量紀錄與產品稽核資料，但目前仍是「各功能自行回報」的狀態，尚未形成：

- 統一結構化日誌。
- 穩定錯誤分類。
- 請求與操作關聯。
- 可支援 SLO 的時間序列指標。
- 告警與本機儀表板。
- 可驗證的敏感資料防護。

因此下一步應先建立契約與允許清單，而不是先挑選監控工具或建立遠端收集平台。
