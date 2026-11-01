# 待改善項（findings）

分組：效能瓶頸（PERF）／資源洩漏（LEAK）／併發與競態（RACE）／逾時與重試（TIME）／
錯誤恢復（RECV）／日誌可觀測性（OBS）。每項含：位置、影響、建議修法、驗證方式、優先級、證據。

> 標示「需程式碼確認」者，表示該模組原始碼未在本次審查視野內，請先以 `驗證方式`
> 重現或推翻，再動手修。所有驗證都用 `tmp_path`／暫存根目錄與假資料，連線需求一律
> 以本地 fake 取代，憑證只用 `FAKE_VALUE_FOR_TEST`。

## 索引

| ID | 標題 | 優先級 |
|---|---|---|
| PERF-01 | 無 FTS5 時搜尋退回 LIKE，大型資料集線性掃描 | P1 |
| PERF-02 | 收件匣一次渲染全部郵件，缺少分頁／虛擬列表 | P2 |
| PERF-03 | Agent 任務每次重建成員包並重複搜尋來源 | P2 |
| PERF-04 | IMAP 同步對大量郵件逐一抓全文，缺少節流與增量 | P1 |
| PERF-05 | 成果卡片列表每次全檔讀取並在記憶體排序 | P2 |
| LEAK-01 | CLI Agent 子程序逾時後未回收，可能殭屍化 | P1 |
| LEAK-02 | HTTP Agent worker 回應未關閉 | P1 |
| LEAK-03 | IMAP 連線在錯誤路徑未登出 | P1 |
| LEAK-04 | 本機產物與用量檔無上限成長 | P2 |
| LEAK-05 | 前端重複渲染與觀察器 | P3 |
| RACE-01 | SQLite 寫入競爭與鎖定 | P0 |
| RACE-02 | 衍生資料重建與同步競態 | P1 |
| RACE-03 | 清除快取與進行中請求競態 | P2 |
| RACE-04 | 跨執行緒共用 SQLite 連線（需程式碼確認） | P0 |
| TIME-01 | openai_compatible 驅動未明確設定逾時 | P1 |
| TIME-02 | IMAP 連線無 socket 逾時 | P1 |
| TIME-03 | 缺少重試與退避策略 | P2 |
| TIME-04 | outbox 背景工作長任務阻塞 | P2 |
| RECV-01 | 單帳號同步失敗隔離（需程式碼確認） | P1 |
| RECV-02 | 成果卡寫入非原子，可能留下半套檔 | P2 |
| RECV-03 | 結構化遷移與版本相容 | P2 |
| RECV-04 | 重啟後排程與撤銷視窗續存 | P2 |
| OBS-01 | 缺乏統一結構化日誌與等級 | P1 |
| OBS-02 | 關鍵路徑缺少耗時與容量指標 | P1 |
| OBS-03 | 錯誤分類不一致，外部回應有洩漏風險 | P1 |
| OBS-04 | `/api/features` 健康與載入錯誤呈現 | P3 |
| OBS-05 | 用量記錄需持續確保不含提示詞 | P2 |

---

## A. 效能瓶頸（PERF）

### PERF-01 無 FTS5 時搜尋退回 LIKE，大型資料集線性掃描
- 位置：`server/features/search.py`（搜尋與索引重建）；`server/yhbmail.py`（`emails` 表）
- 影響：信件數到數千～數萬時，每次搜尋全表掃描，回應時間隨資料量線性成長；
  拖累面板搜尋、聯絡人彙整與「Agent 改寫查詢」流程。
- 建議修法：啟動時偵測 FTS5；無 FTS5 時對 `LIKE` 查詢加上結果上限與必要前綴條件，
  並在 `/api/health` 暴露目前搜尋引擎種類（fts5／like）；把降級行為寫進文件。
  避免在單一請求熱路徑重複搜尋。
- 驗證方式：在 `tmp_path` 建 N=20000 封假信（內容用 `FAKE_VALUE_FOR_TEST`），
  分別在有／無 FTS5 的 SQLite 下量測 `/api/search` P95；斷言降級仍在可接受上限內，
  且結果正確。
- 優先級：P1
- 證據：`ARCHITECTURE.md` §5.4、§10.5；ROADMAP 項目 9（大型資料集效能）。需程式碼確認細節。

### PERF-02 收件匣一次渲染全部郵件，缺少分頁／虛擬列表
- 位置：`ui/index.html`、`ui/modules/mailops.js`（收件匣列表）；對應 `/api/inbox`
- 影響：大型收件匣首次載入 DOM 節點過多，記憶體與首次可互動時間上升，手機版（<760px）更明顯。
- 建議修法：`/api/inbox` 加分頁或 `limit`+cursor；前端虛擬列表或增量載入；
  保留深連結（`#thread=…`）與鍵盤定位行為，避免回歸既有操作。
- 驗證方式：以合成大型資料集量測 time-to-interactive 與 DOM 節點數；
  有 Node 時跑 `node --check`，沒有則跳過，不回歸 Python 核心測試。
- 優先級：P2
- 證據：ROADMAP 項目 9；`ARCHITECTURE.md` §10。

### PERF-03 Agent 任務每次重建成員包並重複搜尋來源
- 位置：`server/features/agents.py`（`_local_sources`、`build_pack`、`run_task`）
- 影響：同一對象短時間多次請求會重複 `list_emails` 與包組合；包過大會拉長外部
  Agent 延遲與 token 成本，也浪費本機 CPU。
- 建議修法：對來源搜尋結果與 persona／brain 片段做短 TTL 快取；明確上限
  （來源數、每段 snippet 長度，現有 `MAX_BODY`／snippet 截斷可保留並集中管理）；
  在回應中附各階段耗時（不含內容）。
- 驗證方式：以假 Agent（回 `FAKE_VALUE_FOR_TEST`）連續呼叫兩次同一對象，
  斷言第二次明顯更快且結果一致；量測 `build_pack` 耗時上限。
- 優先級：P2
- 證據：`server/features/agents.py` 原始碼（可見）。

### PERF-04 IMAP 同步對大量郵件逐一抓全文，缺少節流與增量
- 位置：`server/features/imap.py`、`server/yhbmail.py`（同步協調）
- 影響：大信箱首次同步耗時長；無節流可能觸發供應商限流；同步期間佔用請求資源。
- 建議修法：增量同步（UID 範圍／已有訊息比對）、批次 `UID FETCH`、可設節流與
  單帳號上限；把同步耗時寫入帳號狀態（只記數字，不記主旨／寄件人）。
- 驗證方式：以 `tests/_tpi_imap_fake.py` 擴增的假 IMAP，斷言只發
  `EXAMINE`／`UID SEARCH`／`UID FETCH` 等唯讀命令，並量測批次大小與耗時上限。
- 優先級：P1
- 證據：ROADMAP 項目 5（節流與增量策略）；`ARCHITECTURE.md` §5.2。需程式碼確認現況。

### PERF-05 成果卡片列表每次全檔讀取並在記憶體排序
- 位置：`server/features/agents.py`（`list_deliverables`）
- 影響：卡片增多後，每次切到「成果卡片」都 `glob("*.json")` 並逐檔讀取、排序，
  I/O 隨卡片數線性成長。
- 建議修法：以 mtime 做輕量索引或快取，只在目錄變更時重掃；維持 `limit` 上限；
  或改由 SQLite 記錄卡片索引，與 ROADMAP 的備份／一致性工作互相呼應。
- 驗證方式：在暫存 `data/deliverables/` 建立大量假卡 JSON（`FAKE_VALUE_FOR_TEST`），
  量測 `list_deliverables` 耗時；斷言結果與排序正確。
- 優先級：P2
- 證據：`server/features/agents.py` 原始碼（可見）。

---

## B. 資源洩漏（LEAK）

### LEAK-01 CLI Agent 子程序逾時後未回收，可能殭屍化
- 位置：`server/agent_bridge.py`（`cli` 驅動）
- 影響：反覆觸發 cli driver 逾時會累積殭屍程序與檔案描述子，長期下來拖垮主機。
- 建議修法：統一用 `subprocess.run(..., timeout=...)`，或在逾時路徑明確
  `kill()` + `wait()`；把逾時轉成既有 fallback（本機啟發式）並在回應標示。
- 驗證方式：假 CLI（sleep 超過 `timeout_sec`）斷言拋出逾時、無殘留程序、
  結果回到本機啟發式並標 `fallback`。
- 優先級：P1
- 證據：`agent.example.json` 的 `cli.timeout_sec`；`ARCHITECTURE.md` §5.3。需程式碼確認回收邏輯。

### LEAK-02 HTTP Agent worker 回應未關閉
- 位置：`server/agent_bridge.py`（`http` 驅動）
- 影響：連線未釋放，長跑可能耗盡 socket，尤其 worker 偶發變慢時。
- 建議修法：`with urllib.request.urlopen(req, timeout=...) as r:` 讀取後自動關閉；
  與逾時設定（見 TIME-01）一併處理。
- 驗證方式：假 HTTP worker（回 `FAKE_VALUE_FOR_TEST`）回應後斷言連線關閉、逾時可控。
- 優先級：P1
- 證據：`adapters/README*` 的 http driver。需程式碼確認。

### LEAK-03 IMAP 連線在錯誤路徑未登出
- 位置：`server/features/imap.py`
- 影響：同步例外時 socket 洩漏，可能被供應端視為過多連線而暫時拒連。
- 建議修法：`try/finally` 確保 `logout()`／`close()`；設定 socket 逾時（見 TIME-02）；
  單帳號失敗不影響其他帳號（見 RECV-01）。
- 驗證方式：假 IMAP 在 `EXAMINE` 後拋錯，斷言 `finally` 有登出、無殘留 socket、
  其他帳號不受影響。
- 優先級：P1
- 證據：`ARCHITECTURE.md` §5.2。需程式碼確認。

### LEAK-04 本機產物與用量檔無上限成長
- 位置：`server/features/usage.py`（`data/usage.jsonl`）、技能投影片（`data/slides/`）、
  `data/deliverables/`
- 影響：長期使用磁碟持續成長，沒有保留／輪轉政策，增加備份體積（對應 ROADMAP 項目 1）。
- 建議修法：用量檔依大小或時間輪轉；投影片與成果卡提供保留期或清理提示；
  清理時絕不誤刪草稿、聯絡人、使用者手寫卡片與日曆資料。
- 驗證方式：在暫存根目錄模擬大量寫入，斷言輪轉後檔數／大小受控，且不觸及受保留資料。
- 優先級：P2
- 證據：`README`（usage.jsonl）；`ARCHITECTURE.md` §4.2。

### LEAK-05 前端重複渲染與觀察器
- 位置：`ui/modules/agents.js`（`MutationObserver`、`renderPane`）
- 影響：語言切換或狀態變更反覆 `innerHTML` 重建，昂貴渲染與潛在重複事件綁定；
  非記憶體洩漏但屬資源浪費。
- 建議修法：渲染加髒檢查或以 `requestAnimationFrame` 合併；移除舊觀察器或去重；
  避免在 observer 內無條件全量重繪。
- 優先級：P3
- 證據：`ui/modules/agents.js` 原始碼（可見）。

---

## C. 併發與競態（RACE）

### RACE-01 SQLite 寫入競爭與鎖定
- 位置：`server/yhbmail.py`（連線與交易）、`server/app.py`（背景 outbox 工作）
- 影響：多執行緒 HTTP + 背景工作 + 同步同時寫入，可能出現 `database is locked`
  或長交易阻塞讀取；大批次操作特別明顯（ROADMAP 項目 8 已預警）。
- 建議修法：啟用 WAL 與 `busy_timeout`；保持交易短小；每執行緒獨立連線或將寫入
  序列化；背景工作與請求處理分離，避免長任務持鎖。
- 驗證方式：暫存 DB 上多執行緒併發寫入，斷言無 `locked` 錯誤、資料最終一致。
- 優先級：P0
- 證據：ROADMAP 項目 2／8；`ARCHITECTURE.md` §10.7。需程式碼確認現況。

### RACE-02 衍生資料重建與同步競態
- 位置：`server/persona.py`、`server/second_brain.py`、`server/features/search.py`
- 影響：重建途中郵件被寫入，可能產生重複卡片或讀到半成品索引；使用者看到過期結果。
- 建議修法：以穩定版本簽章驅動「可重入」衍生流程；同一時間只跑一個重建
  （single-flight）；單一壞卡隔離，不阻塞整體索引（對應 ROADMAP 項目 2）。
- 驗證方式：併發「同步寫信 + 重建索引」，斷言無重複卡、索引最終一致、可重入。
- 優先級：P1
- 證據：ROADMAP 項目 2。需程式碼確認。

### RACE-03 清除快取與進行中請求競態
- 位置：`server/features/cache.py`
- 影響：`clear` 與讀取同時發生，可能讀到剛被清除的資料或暫時性錯誤。
- 建議修法：清除在鎖內進行；請求端對暫時性空結果重試一次；嚴格維持
  `ARCHITECTURE.md` §5.9 的清除語意（保留草稿、手寫卡、本機／匯入日曆）。
- 驗證方式：併發 `clear` + inbox 讀取，斷言無未處理例外、最終狀態符合語意。
- 優先級：P2
- 證據：`ARCHITECTURE.md` §5.9。

### RACE-04 跨執行緒共用 SQLite 連線（需程式碼確認）
- 位置：`server/app.py`、`server/yhbmail.py`
- 影響：若單一連線物件被多執行緒共用（ThreadingHTTP 模型下），可能資料競爭或
  intermittent 錯誤；這是 P0 級「先確認」項。
- 建議修法：改用執行緒本地連線，或加鎖序列化；明確設定 `check_same_thread`；
  與 RACE-01 一併處理。
- 驗證方式：併發打寫入型端點，觀察是否出現 race 或 `locked`；以暫存 DB 重現。
- 優先級：P0
- 證據：`ARCHITECTURE.md` §2（標準函式庫 HTTP 多請求）推論；需程式碼確認。

---

## D. 逾時與重試（TIME）

### TIME-01 openai_compatible 驅動未明確設定逾時
- 位置：`server/agent_bridge.py`（`openai_compatible` 驅動）
- 影響：端點無回應時請求執行緒可能無限期等待，拖垮面板與 MCP 以外的 HTTP 流程；
  設定檔目前只有 `cli`／`http` 有 `timeout_sec`。
- 建議修法：所有驅動都要有逾時；為 `openai_compatible` 增加預設逾時與可設定值；
  逾時一律回到本機啟發式並標 `fallback`。
- 驗證方式：假端點永久 hang，斷言在逾時內回到本機啟發式且回應含 fallback 標示。
- 優先級：P1
- 證據：`agent.example.json` 僅 `cli`／`http` 有 `timeout_sec`。需程式碼確認。

### TIME-02 IMAP 連線無 socket 逾時
- 位置：`server/features/imap.py`
- 影響：伺服器不回應會讓同步卡住，可能阻塞相關請求與背景節奏。
- 建議修法：設定 socket 逾時與單帳號逾時；失敗記為該帳號錯誤與上次狀態，
  不阻塞其他帳號（搭配 RECV-01、LEAK-03）。
- 驗證方式：假 IMAP 不回話，斷言在逾時內失敗並記錄狀態，其他帳號繼續。
- 優先級：P1
- 證據：`ARCHITECTURE.md` §5.2。需程式碼確認。

### TIME-03 缺少重試與退避策略
- 位置：`server/agent_bridge.py`、`server/features/imap.py`
- 影響：瞬時網路失敗即整體 fallback，體驗差；若日後改重試又無退避，可能加重上游負載。
- 建議修法：僅對冪等唯讀操作做有界重試（指數退避 + 抖動、 attempts 上限）；
  重試事件記 log（只記次數與錯誤類別，不含內容）；與 TIME-01／TIME-02 的逾時共存。
- 驗證方式：假上游前兩次失敗、第三次成功，斷言重試次數與最終成功；
  再測全部失敗時有界停止並 fallback。
- 優先級：P2
- 證據：架構推論。需程式碼確認。

### TIME-04 outbox 背景工作長任務阻塞
- 位置：`server/app.py`（背景工作）、`server/features/outbox.py`
- 影響：到期檢查若同步做重活，延遲請求回應，違背「單行程也要保持可互動」。
- 建議修法：tick 保持輕量，重活交背景執行緒；記錄 tick 耗時並設上限（搭配 OBS-02）。
- 驗證方式：量測 tick 耗時上限；併發請求不受 tick 影響。
- 優先級：P2
- 證據：`ARCHITECTURE.md` §2（背景到期檢查）。

---

## E. 錯誤恢復（RECV）

### RECV-01 單帳號同步失敗隔離（需程式碼確認）
- 位置：`server/yhbmail.py`（同步協調）、`server/features/providers.py`
- 影響：若未隔離，一個帳號失敗會中斷全部同步，使用者誤以為全壞。
- 建議修法：逐帳號 `try/except`，記錄該帳號錯誤與上次狀態，繼續其他帳號；
  UI 與 `/api/providers` 對同一狀態呈現一致（對應 ROADMAP 項目 3）。
- 驗證方式：兩帳號一好一壞，斷言好帳號仍同步、壞帳號有錯誤狀態、API 一致。
- 優先級：P1
- 證據：ROADMAP 項目 3；`ARCHITECTURE.md` §5.2(5)。需程式碼確認。

### RECV-02 成果卡寫入非原子，可能留下半套檔
- 位置：`server/features/agents.py`（`save_deliverable`）
- 影響：依序寫 `md`／`html`／`json`，途中當掉會留下不一致的一組檔；
  前端 preview 可能缺檔或读到半成品。
- 建議修法：先寫暫存再原子 `rename`；或先寫 `json` 當 manifest 最後落地；
  讀取時容忍缺檔（現有 `list_deliverables` 已略過壞 JSON，可延伸）。
- 驗證方式：模擬寫入中斷，斷言不出現半套卡或能安全略過，不影響其他卡。
- 優先級：P2
- 證據：`server/features/agents.py` 原始碼（可見）。

### RECV-03 結構化遷移與版本相容
- 位置：`server/yhbmail.py`（schema）、各 feature 資料表
- 影響：升級時 schema 變更可能失敗或資料遺失；本機優先產品最怕升級掉資料。
- 建議修法：可回復、可驗證的遷移；啟動時版本檢查；遷移前建議先備份
  （對應 ROADMAP 項目 1）。
- 驗證方式：以暫存 DB 測升級／降級路徑，斷言資料保留、可重跑。
- 優先級：P2
- 證據：ROADMAP 共同完成定義 #6。

### RECV-04 重啟後排程與撤銷視窗續存
- 位置：`server/features/outbox.py`
- 影響：重啟應保留排程項目與倒數撤銷能力，否則使用者誤按或漏寄。
- 建議修法：確認狀態持久化；啟動時重建到期檢查；撤銷視窗以持久時間為準。
- 驗證方式：暫存環境模擬重啟，斷言排程與 undo 仍有效、時間窗正確。
- 優先級：P2
- 證據：`ARCHITECTURE.md` §5.5。

---

## F. 日誌可觀測性（OBS）

### OBS-01 缺乏統一結構化日誌與等級
- 位置：`server/app.py` 與各 feature
- 影響：問題難追蹤；目前錯誤多只回給呼叫端，服務端沒有可查的痕跡。
- 建議修法：以 stdlib `logging` 建立統一 logger，含等級與模組名；
  **嚴禁**記錄郵件內文、主旨、寄件人、案件或當事人資料、提示詞、模型回答、金鑰；
  只記事件類型、錯誤類別、HTTP 狀態、耗時與計數。
- 驗證方式：斷言日誌範本不含內文／金鑰；用掃描式測試檢查輸出無敏感字串。
- 優先級：P1
- 證據：架構推論；`CONTRIBUTING*` 安全規範。需程式碼確認現況。

### OBS-02 關鍵路徑缺少耗時與容量指標
- 位置：同步、Agent 呼叫、搜尋、背景 tick
- 影響：無法量化效能改善，也沒有上限告警；ROADMAP 也要求「顯示最近一次同步耗時」。
- 建議修法：記錄每次同步／Agent／搜尋的耗時與結果數；可在 `/api/health` 暴露彙總
  （只含數字，不含內容）。
- 驗證方式：斷言健康端點回傳計數／耗時且無 PII；量測值隨合成負載可觀成長。
- 優先級：P1
- 證據：ROADMAP 項目 3。

### OBS-03 錯誤分類不一致，外部回應有洩漏風險
- 位置：各 feature 錯誤處理；`server/features/agents.py` 已有 `error_label` 可推廣
- 影響：上游錯誤文字可能含端點回應、CLI stderr、提示詞，直接回給使用者即洩漏。
- 建議修法：全站統一「只回例外類別 + HTTP 狀態」的錯誤正規化（複用 `agents.py` 模式）；
  IMAP／CLI 錯誤先正規化再顯示（對應 ROADMAP 項目 3 風險）。
- 驗證方式：假上游回傳含敏感字串的錯誤，斷言 API 不回傳該字串、只回類別與狀態。
- 優先級：P1
- 證據：`server/features/agents.py` `error_label`（可見）；ROADMAP 項目 3。

### OBS-04 `/api/features` 健康與載入錯誤呈現
- 位置：`server/features/plugins.py`
- 影響：外掛錯誤需可診斷，但不能洩內部路徑或郵件內容（對應 ROADMAP 項目 10）。
- 建議修法：顯示健康狀態與可執行訊息，移除完整檔案路徑；保留「Python 外掛為受信任
  程式碼、非沙箱」的明確警告。
- 驗證方式：置入壞外掛，斷言服務仍可啟動、清單顯示錯誤、無敏感路徑。
- 優先級：P3
- 證據：ROADMAP 項目 10。

### OBS-05 用量記錄需持續確保不含提示詞
- 位置：`server/features/usage.py`
- 影響：產品承諾「不記提示詞、回答或金鑰」，需靠測試持續把關，避免日後回归。
- 建議修法：加測試斷言 `usage.jsonl` 每行只有計數與時間戳，無提示詞／回答／金鑰；
  只回環境變數名稱、不回值（沿用 providers 做法）。
- 驗證方式：斷言行格式與欄位集合。
- 優先級：P2
- 證據：`README`（用量說明）；`ARCHITECTURE.md` §8.2。
