# openinbox 效能與可靠性審查

> 審查性質：文件型審查；本輪只新增本報告，不修改程式、測試、workflow 或設定。  
> 審查基準：本次提供之 default branch 內容快照。定位以「檔案＋函式／符號」為準，避免行號漂移。  
> 資料安全：本報告不包含實際信件內容、地址、憑證、token、金鑰或案件資料；後續驗證一律使用 `FAKE_VALUE_FOR_TEST` 等明顯假值，且不得連線正式服務。

## 1. 執行摘要

本次審查聚焦六個面向：**效能瓶頸、資源洩漏、併發／競態、逾時與重試、錯誤恢復、日誌可觀測性**。

最需要優先處理的风险如下：

1. **對外 Agent 工作缺少可證明的端到端 deadline 與取消機制**：HTTP handler、瀏覽器 fetch 與 overnight 總流程都需要共同 deadline，不能只依賴底層 driver 的局部 timeout。
2. **昂貴的 Agent 呼叫只有前端忙碌停用，後端沒有併發 admission control**：多視窗、多个分頁或重送仍可同時觸發模型呼叫，造成成本失控、上游飽和與資源累積。
3. **多處 JSON／索引檔採覆寫式、非原子寫入**：`persona.py`、`second_brain.py`、`agents.py` 在崩潰或並行請求下可能留下半檔、壞 JSON 或互相覆寫。
4. **本機產物與日誌缺少生命週期管理**：deliverable 同時保存三種重複內容且永久累積；Second Brain 舊卡片不回收；usage JSONL 與 overnight log 亦未見輪替策略。
5. **Second Brain 搜尋與 deliverable 清單都會隨資料量線性惡化**：目前分別是全量記憶體搜尋、讀取並解析所有 JSON 後才切片。
6. **overnight 缺少單例鎖**：cron、CLI 與 API 同時執行時可能重複同步、建立草稿或互相覆寫 brief。
7. **fallback 雖能維持可用性，但會把根因壓成單一錯誤字串**：空回應、遠端逾時、HTTP 4xx、解析失敗與本機 fallback 沒有可觀測差異，容易形成靜默降級。
8. **缺少業務層結構化紀錄與 correlation ID**：目前 reviewed modules 沒有足以回答「哪次請求、哪個階段、耗時多久、是否 fallback、錯誤在哪」的紀錄。

建議先處理 **PRF-01～PRF-10**，再處理查詢擴充性與 UI race；同時完成 **PRF-G01～PRF-G06** 的核心檔案驗證閘門。這些閘門不代表已確認有錯，而是因本次未提供 `yhbmail.py`、`agent_bridge.py`、`app.py` 等內文，不能負責任地宣稱其不存在問題。

---

## 2. 優先級定義

| 優先級 | 定義 | 處理期待 |
|---|---|---|
| **P0** | 可能造成資料毀損、敏感資訊外洩或不可逆重大事故 | 立即停止相關部署並修復 |
| **P1** | 可能造成錯誤結果、程序永久卡住、重複付費、資料遺失或常見可用性事故 | 第一個修復批次 |
| **P2** | 資料量或流量成長後會明顯惡化，或可觀測性仍不足 | 第二個修復批次 |
| **P3** | 防禦性強化、非核心路徑或長期技術債 | 排入維護 backlog |

本次沒有足夠證據判定 P0；以下項目最高為 P1。

---

## 3. 審查範圍與可信度

### 3.1 已取得並直接審查的主要程式

- `server/features/agents.py`
- `ui/modules/agents.js`
- `server/persona.py`
- `server/second_brain.py`
- `scripts/overnight.py`
- `scripts/smoke.sh`
- `README.md`、`README.zh-Hant.md`
- 相關 feature 狀態文件與測試清單

### 3.2 檔案存在但本次未提供內文的核心位置

下列檔案出現在 repository file list，但本輪可用內容未含其實作，因此以下只能列為「發布前必須驗證的閘門」，不能當成已確認缺陷：

- `server/app.py`
- `server/yhbmail.py`
- `server/agent_bridge.py`
- `server/features/imap.py`
- `server/features/cache.py`
- `server/features/usage.py`
- `server/features/overnight.py`
- `server/features/rules.py`
- `server/features/mailops.py`

### 3.3 審查限制

- 本輪沒有連線任何正式郵件、行事曆、模型或 HTTP 服務。
- 沒有執行 benchmark；數字型目標均為建議驗收值，不是目前實測值。
- 本報告只提出改善方案；受「只能新增 `docs/fmb-perf/` Markdown」限制，未直接修補程式。

---

## 4. 風險總覽

| ID | 問題 | 類別 | 優先級 | 判定 |
|---|---|---|---|---|
| PRF-01 | 缺少端到端 deadline、取消與逾時收斂 | 逾時／資源 | P1 | 可見層確認；底層待驗證 |
| PRF-02 | 昂貴 Agent endpoint 無後端併發與配額保護 | 併發／成本 | P1 | feature 層確認 |
| PRF-03 | overnight 可重疊執行且 brief 非原子發布 | 競態／可靠性 | P1 | 已確認 |
| PRF-04 | deliverable 三檔非原子寫入 | 競態／錯誤恢復 | P1 | 已確認 |
| PRF-05 | persona 並行 rebuild 可產生壞 JSON 與版本不一致 | 競態／資料完整性 | P1 | 已確認 |
| PRF-06 | Second Brain 有 lost update、壞 index 與孤兒卡片 | 競態／資源洩漏 | P1 | 已確認 |
| PRF-07 | Agent 輸出與 deliverable 檔案無大小上限 | 記憶體／磁碟 | P1 | 已確認 |
| PRF-08 | 重試、退避、熔斷與 fallback 原因未分級 | 重試／錯誤恢復 | P1 | 可見層確認；bridge 待驗證 |
| PRF-09 | 缺少業務層結構化日誌與 correlation ID | 可觀測性 | P1 | 已確認 |
| PRF-10 | deliverable 全目錄掃描、內容重複且無保留策略 | 效能／資源洩漏 | P1 | 已確認 |
| PRF-11 | Second Brain 搜尋與 index 為全量線性掃描 | 效能 | P2 | 已確認 |
| PRF-12 | persona 缺檔時會在請求路徑同步完整重建 | 效能／競態 | P2 | 已確認 |
| PRF-13 | Agent context 沒有可見的位元組／token budget | 效能／成本 | P2 | 可見層確認；來源待驗證 |
| PRF-14 | UI 非同步請求可能以舊回應覆蓋新狀態 | 競態／UI | P2 | 已確認 |
| PRF-15 | usage JSONL 與 cron log 缺少輪替策略 | 資源／可觀測性 | P2 | 文件證據；實作待確認 |
| PRF-16 | overnight 缺少逐階段時間、錯誤分類與 deadline | 可觀測性／逾時 | P2 | 已確認 |
| PRF-17 | smoke harness 缺通用逾時與可靠 readiness | 測試可靠性 | P2 | 部分確認；workflow 待核對 |
| PRF-G01 | SQLite 連線、交易與 busy timeout | 併發／資料完整性 | P1 | 驗證閘門 |
| PRF-G02 | Agent transport／CLI 子程序生命週期 | 逾時／資源洩漏 | P1 | 驗證閘門 |
| PRF-G03 | IMAP socket timeout 與 session 清理 | 資源洩漏／逾時 | P1 | 驗證閘門 |
| PRF-G04 | mail sync 的冪等性與部分失敗隔離 | 錯誤恢復／競態 | P1 | 驗證閘門 |
| PRF-G05 | HTTP server 執行模型與 request body 限制 | 併發／資源 | P1 | 驗證閘門 |
| PRF-G06 | cache clear、規則與設定檔的並行一致性 | 競態／錯誤恢復 | P2 | 驗證閘門 |

---

## 5. 可執行改善項目

## PRF-01：建立端到端 deadline、取消與逾時收斂

- **分類**：逾時、資源洩漏、可靠性
- **判定**：可見層確認；`agent_bridge.py` 是否已有完整 timeout 尚待驗證。
- **位置**：
  - `server/features/agents.py`：`run_task()`、`task()`、`mention()`
  - `ui/modules/agents.js`：`getJSON()`、`postJSON()`、preview fetch
  - `scripts/overnight.py`：`main()` 對 `overnight.run()` 的單次呼叫
  - `server/agent_bridge.py`：需確認 `_openai()`、`_cli()`、`_http()`
- **證據**：
  - `run_task()` 在 HTTP request handler 內同步呼叫 driver，feature 層沒有 deadline 或 cancellation token。
  - 瀏覽器 `fetch()` 沒有 `AbortController` 或 client-side timeout。
  - overnight 沒有用「總剩餘時間」限制同步、分流、規則與草稿各階段。
- **影響**：
  - 上游不回應時，request handler、UI 按鈕或 overnight 程序可能長時間停住。
  - CLI driver 若未正確管理子程序群組，可能留下孤兒 process。
  - 多個停滯請求會累積 thread、socket、child process 與檔案描述符。
  - UI 即使收到逾時，使用者仍可能重複點擊，形成重複呼叫。
- **建議修法**：
  1. 建立共用 `RequestBudget`，以 `time.monotonic()` 計算剩餘時間；所有階段只使用剩餘 deadline，不得各自重新給完整 timeout。
  2. 預設起始值：transport connect 5 秒、read 60 秒、單次 Agent 總計 120 秒；設定可調，但下限不可為零。
  3. `agent_bridge` 接受 deadline：
     - HTTP 設定 connect/read timeout，且在讀 body 時同時檢查總 deadline。
     - CLI 使用 `timeout=remaining`，並以獨立 process group 啟動；逾時先 TERM，短暫等待後 KILL 整組。
     - 回傳 typed error，例如 `AgentTimeout`、`AgentConnectError`、`AgentHTTPError`。
  4. HTTP API 遇 deadline 回 `504` 與固定、無敏感內容的錯誤碼；不得回傳例外本文、endpoint body 或 CLI stderr。
  5. UI 使用 `AbortController`，在 server deadline 前留 5 秒中止，並在 view 切換時取消不再需要的請求。
  6. overnight 設總 deadline；每個帳號同步再套用子 deadline，剩餘時間不足時跳過後續帳號並留下明確摘要。
- **驗證方式**：
  1. 在 `127.0.0.1` 啟動 ephemeral port 的假 HTTP server，依 query 決定延遲或永不回應。
  2. 驗證 API 在總 deadline 加小量裕裕內回 `504`，且不記錄假 server body。
  3. 驗證 UI abort 後不再寫入舊 view，且按鈕恢復可操作。
  4. 用本機假 CLI 啟動長駐 child，觸發逾時後以 process listing／PID 確認 child group 已結束。
  5. 連續執行逾時案例 100 次，確認 FD、thread 與 child process 數量回到基準附近。
- **優先級**：**P1**
- **完成定義**：每一條對外路徑都有可觀測的 connect/read/total deadline；逾時不留下 child、socket 或 SQLite transaction。

## PRF-02：為昂貴 Agent endpoint 增加後端 admission control

- **分類**：併發、成本、資源
- **判定**：`server/features/agents.py` 層確認；`app.py` 可能有全域限制，但本輪未提供內文。
- **位置**：
  - `server/features/agents.py`：`task()`、`mention()`
  - `ui/modules/agents.js`：`view.busy`
  - `server/app.py`：需確認是否已有 server-wide limiter
- **證據**：
  - UI 的 `view.busy` 只能防同一頁面內的重複操作。
  - feature handler 沒有 semaphore、佇列上限、每分鐘呼叫上限或單次預算。
  - `local_origin()` 是來源檢查，不是併發控制。
- **影響**：
  - 多視窗、多分頁、平行 API client 或重送可同時觸發多個模型呼叫。
  - 可能超過模型服務配額、增加費用，並使本機記憶體、child process 與 socket 壓力上升。
  - 收到含 mention 的快取信件也可能觸發昂貴路徑，缺少每日成本上限。
- **建議修法**：
  1. 在 server 層建立 process-wide bounded semaphore；保守預設最多 **2** 個外部 Agent 呼叫同時執行。
  2. 佇列上限預設 8；滿載時回 `429` 並附 `Retry-After`，不要無限排隊。
  3. 加入 request idempotency key：同一 key 在短時間內重送時回傳既有結果或明確拒絕重複執行。
  4. 對每個 HTTP request、CLI run 與 overnight run 設定最大外部呼叫次數；不得只靠前端。
  5. 對含外部內容的 mention 預設先 dry-run／要求明確使用者動作，再允許實際模型呼叫。
  6. 記錄 active、queued、rejected、completed counter，不記錄呼叫內容。
- **驗證方式**：
  1. 在本機同時送 20 個 Agent task，fake driver 記錄最大 active 數；應不超過 2。
  2. 超過 queue cap 時收到 `429`，且 fake driver 呼叫數維持上限。
  3. 以相同 idempotency key 連送兩次，確認最多執行一次。
  4. 驗證拒絕與逾時路徑也會釋放 semaphore。
- **優先級**：**P1**
- **完成定義**：不論 client 數量，外部 Agent 併發與每次呼叫成本都受到 server-side hard limit。

## PRF-03：overnight 單例鎖與原子 brief 發布

- **分類**：競態、錯誤恢復、資源
- **判定**：已確認。
- **位置**：`scripts/overnight.py`：`main()`；`server/features/overnight.py`：API 入口需共用同一鎖。
- **證據**：`main()` 直接執行 `overnight.run()`，沒有 lock、run ID 或「已在執行」檢查。cron 範例本身也可能與前次執行重疊。
- **影響**：
  - 同步、草稿建立、規則套用與 brief 寫入可能同時發生。
  - 同一 DB 會承受重複 writer，增加鎖衝突與重複草稿。
  - 多個程序可能同時覆寫 `latest.md`，留下混合或半寫檔。
- **建議修法**：
  1. 在 `data/locks/` 建立跨 CLI／API 共用的 single-flight lock。
  2. Unix 使用標準函式庫 `fcntl.flock`；Windows 提供 `msvcrt` 等價實作，不新增 pip 相依。
  3. 取得鎖時寫入不含敏感內容的 `pid`、started-at、run-id；逾時只回「已有執行中」，不要洩漏信件資訊。
  4. 每次執行寫入唯一 run directory；完成後以 `os.replace()` 原子更新 `latest.md`。
  5. 鎖釋放必須放在 `finally`；程式崩潰時由作業系統釋放檔案鎖。
- **驗證方式**：
  1. 以 barrier 讓兩個本機程序同時進入 `main()`；應只有一個進入核心流程，另一個以固定非零碼退出。
  2. 強制終止持有者後重新執行，確認 stale metadata 不會永久阻止執行。
  3. 連續 20 輪皆只有一個有效 run，且 `latest.md` 永遠可完整解析。
- **優先級**：**P1**
- **完成定義**：CLI、cron 與 API 共用同一 single-flight 機制，brief 只會由完整 run 原子發布。

## PRF-04：將 deliverable 改成可提交、可恢復的原子發布

- **分類**：競態、資料完整性、錯誤恢復
- **判定**：已確認。
- **位置**：`server/features/agents.py`：`save_deliverable()`、`list_deliverables()`、`read_deliverable()`。
- **證據**：
  - 同一 deliverable 依序以 `write_text()` 寫入 `.md`、`.html`、`.json`。
  - 寫入不是 temp-file + `os.replace()`，也沒有 group commit marker。
  - `list_deliverables()` 直接讀所有 JSON；`read_deliverable()` 直接 `read_bytes()`。
- **影響**：
  - 寫到一半當機或當掉電會留下部分檔案。
  - list 可能看到 JSON 與 MD／HTML 不一致的卡片。
  - 已知 ID 的讀取可能命中半寫入內容。
- **建議修法**：
  1. 每個 deliverable 使用不可預測唯一 ID；保留時間戳供顯示，但不要只靠微秒時間作唯一性。
  2. 在同目錄建立 temporary files，flush 並完成需要的 fsync 後逐檔 `os.replace()`。
  3. 以 metadata JSON 作 commit marker；只有 marker 存在且驗證通過的項目才可由 API 列出或預覽。
  4. 啟動或讀取時清理已知 temporary suffix；不要刪除不屬於本流程的檔案。
  5. 將 canonical content 與衍生 HTML 分離，避免同一內容無條件保存三份。
- **驗證方式**：
  1. 對第二或第三次寫入注入 `OSError`，確認 API 不會列出半成品。
  2. 在 50 個並行 task 下確認所有 ID 唯一，且每個可列項目都可讀到完整 MD／HTML／metadata。
  3. 模擬 process kill，確認重新啟動後可辨識並清理未提交 temporary 檔。
- **優先級**：**P1**
- **完成定義**：任何時間點都只存在「完整可讀」或「尚未提交」兩種 deliverable 狀態，不會出現已公開的半檔。

## PRF-05：修正 persona 的並行 rebuild、原子寫入與損壞恢復

- **分類**：競態、資料完整性、錯誤恢復
- **判定**：已確認。
- **位置**：`server/persona.py`：`rebuild()`、`load()`。
- **證據**：
  - `load()` 在檔案不存在時直接呼叫 `rebuild()`；並行請求可同時進入完整掃描與寫檔。
  - JSON 與 Markdown 都直接覆寫，沒有 lock 或 atomic replace。
  - `load()` 對損壞 JSON 沒有 recovery path。
- **影響**：
  - 兩個請求可能交錯覆寫 JSON 與 MD，造成解析錯誤或兩種格式版本不一致。
  - 第一個並行讀取可能碰到尚未完成的 JSON。
  - persona 檔損壞後，持續使 Agent、搜尋或相關 API 失敗。
- **建議修法**：
  1. 以 process-wide lock 保護 rebuild 與檔案發布；或使用 SQLite transaction 當協調點。
  2. JSON 與 MD 都採 temp-file + `os.replace()`；JSON 內加入單調遞增 `revision`，MD 標示相同 revision。
  3. `load()` 先驗證 JSON schema 與 revision；損壞時隔離損壞檔、記錄安全錯誤碼，再以 deterministic fallback 重建。
  4. 不在一般 GET request 內做完整掃描；啟動時預熱，之後由 sync watermark 觸發增量或背景重建。
  5. 以檔案 mtime／revision 作記憶體 cache key，避免每次 request 重讀與重算。
- **驗證方式**：
  1. 刪除 persona 後並行執行 50 次 `load()`；所有呼叫成功，JSON 與 MD revision 一致。
  2. 注入壞 JSON，確認會安全降級、留下不含內容的錯誤紀錄，且不反覆無限重建。
  3. 在寫 MD 前強制失敗，確認舊 JSON／MD 仍可讀且 revision 不倒退。
- **優先級**：**P1**
- **完成定義**：並行讀取不會產生壞檔；persona 損壞可自動復原且不會形成 rebuild storm。

## PRF-06：Second Brain 改為交易式儲存、清除孤兒卡片並避免 lost update

- **分類**：競態、資源洩漏、資料完整性
- **判定**：已確認。
- **位置**：`server/second_brain.py`：`rebuild()`、`load()`、`add_card()`、`_write_card()`。
- **證據**：
  - `add_card()` 採「讀 index → 修改記憶體 → 覆寫 index」的 read-modify-write；並行呼叫會互相覆寫。
  - `rebuild()` 覆寫 `INDEX`，但不會移除已不存在 source 對應的舊 Markdown。
  - 卡片內容同時存在於 Markdown 與 `vault/index.json` 完整 card 物件中。
- **影響**：
  - 同時新增或修改卡片可能遺失部分更新。
  - 舊卡片永久殘留，造成磁碟、搜尋與人工理解上的累積錯誤。
  - `index.json` 隨內容線性增大，`load()` 每次都需讀入完整 bodies。
- **建議修法**：
  1. 短期先加跨行程 lock 與 atomic index replace，確保 `add_card()` 不會 lost update。
  2. 中期以既有 SQLite 作 canonical store；卡片內容只存一份，Markdown 視為可重建 projection。
  3. 每次 rebuild 以 source-id manifest 計算新增／更新／刪除，刪除已失效 projection。
  4. 大量卡片不要把完整 body 放入 metadata index；index 僅保留 id、title、kind、source、revision、path、size。
  5. 對使用者自建 note 與自動衍生卡片分開管理，避免 rebuild 刪除使用者原創內容。
- **驗證方式**：
  1. 100 個程序／thread 同時 `add_card()`，最後所有 ID 都存在且內容符合預期。
  2. 在 index 寫入時注入例外，確認舊 index 仍可解析。
  3. 移除一個來源後 rebuild，確認其 projection 被移除；使用者 note 仍保留。
  4. 對 10,000 張卡片量測 `load()` 記憶體與時間，確認不隨完整 body 總量成長。
- **優先級**：**P1**
- **完成定義**：並行新增不丟資料；rebuild 可清掉孤兒衍生卡片；metadata index 不重複儲存完整內容。

## PRF-07：限制 Agent 輸出、衍生檔與讀取大小

- **分類**：記憶體、磁碟、DoS 防禦
- **判定**：已確認。
- **位置**：`server/features/agents.py`：`MAX_BODY`、`run_task()`、`save_deliverable()`、`read_deliverable()`。
- **證據**：`MAX_BODY` 只限制 mention 輸入；外部 Agent 回傳文字沒有上限，並會被寫入 MD、HTML、JSON，再完整回傳給瀏覽器。
- **影響**：
  - 單次異常或惡意大回應可佔用大量記憶體、磁碟與 API response buffer。
  - HTML 轉換可能進一步放大磁碟使用量。
  - `read_deliverable()` 的 `read_bytes()` 會把整檔載入記憶體。
- **建議修法**：
  1. 對 Agent 原始回應設定 hard limit；保守起始值為 **256 KiB**。
  2. 超限時不要默默寫入；回固定 `502`／`413` 類型的安全錯誤，記錄 `output_bytes` 與 `output_truncated=false`。
  3. 若產品需要局部呈現，改為明確的 bounded preview，並在資料模型標示已截斷；不得假裝完整。
  4. `read_deliverable()` 讀前先 `stat()`，超過上限拒絕；最好採固定大小 chunk streaming。
  5. 對 API request body 另設上限，且必須在完整解析 JSON 前攔截。
- **驗證方式**：
  1. 本機 fake driver 回傳大於上限的純假文字，確認 API 拒絕且不產生 deliverable。
  2. 寫入一個大 fixture 後，確認讀取端不會無上限配置記憶體。
  3. 驗證邊界值剛好等於限制時可成功，超過 1 byte 時失敗。
- **優先級**：**P1**
- **完成定義**：任何單一模型回應或 deliverable 都不能造成無界記憶體或磁碟配置。

## PRF-08：明確化重試、退避、熔斷與 fallback 原因

- **分類**：重試、錯誤恢復、成本
- **判定**：可見 feature 層確認；`agent_bridge.py` 可能有部分重試，尚待驗證。
- **位置**：`server/features/agents.py`：`run_task()`、`error_label()`；`server/agent_bridge.py`：driver 實作待驗證。
- **證據**：
  - `except Exception` 會將所有錯誤直接降級為本機 fallback。
  - 空字串回應會設為 fallback，但 `error` 可能仍為 `None`。
  - 可見層沒有 attempt、backoff、Retry-After、circuit state 或錯誤分類。
- **影響**：
  - 暫時性網路故障會立即放棄，沒有機會恢復。
  - 所有根因被壓成 exception class／HTTP status，無法分辨 timeout、429、4xx、解析錯誤與空回應。
  - 對可能已計費或已受理的模型呼叫盲目重試，可能重複扣費。
- **建議修法**：
  1. 定義明確 outcome：`ok`、`empty_response`、`timeout`、`connect_error`、`http_4xx`、`http_5xx`、`invalid_response`、`local_fallback`、`cancelled`。
  2. 只有可判定尚未被上游受理的 transient error 才重試；預設最多 2 次，使用 exponential backoff + jitter，並尊重 `Retry-After`。
  3. 若 driver 支援 idempotency key，才允許對逾時後結果不明確的呼叫重試；否則不自動重送可能計費的操作。
  4. 連續失敗時開啟短暫 circuit breaker，避免每個 UI click 都打到失效上游。
  5. 空回應必須記為 `empty_response`；fallback 原因要保留，但回應中不得包含原始 exception message。
  6. 以 typed exception 取代從 exception 字串搜尋 HTTP status；避免意外處理 endpoint body 或 CLI stderr。
- **驗證方式**：
  1. 本機 fake server 依序回 `429`、`503`、成功，驗證 backoff 次數與最終結果。
  2. fake server 回 `400`，確認不重試。
  3. 回空 body，確認 outcome 明確為 `empty_response`。
  4. 模擬 request 已送達但讀取逾時，確認沒有 idempotency 時不自動重送計費呼叫。
- **優先級**：**P1**
- **完成定義**：每一種失敗都有穩定、可測試的分類；重試不超出 deadline，且不重複計費。

## PRF-09：加入業務層結構化日誌、correlation ID 與本機指標

- **分類**：可觀測性、錯誤恢復
- **判定**：已確認。
- **位置**：
  - `server/features/agents.py`
  - `server/persona.py`
  - `server/second_brain.py`
  - `scripts/overnight.py`
  - `server/app.py`（需補 request ID 與 access log）
- **證據**：reviewed modules 沒有使用 `logging` 發出可搜尋事件；多處只回傳錯誤字串、靜默跳過壞檔或只在 CLI 最後印出摘要。
- **影響**：
  - 無法從日誌回答「哪個 request 慢、是否 fallback、哪個帳號失敗、是否產生孤兒檔」。
  - 壞 deliverable JSON 會被靜默忽略，磁碟與資料一致性问题不易察覺。
  - 多個 API 同時執行時，缺乏 correlation ID 使競態難以重現。
- **建議修法**：
  1. 使用 Python 標準函式庫 `logging`，輸出 JSON lines 至 stderr 或本機 log；不新增外部 telemetry。
  2. 每個 HTTP request 產生 `request_id`；每個 overnight run 產生 `run_id`；跨模組傳遞但不要放進 URL。
  3. 建議事件：`agent.run.start`、`agent.run.finish`、`agent.fallback`、`deliverable.publish`、`persona.rebuild`、`brain.rebuild`、`overnight.stage`、`sync.account.finish`。
  4. 建議欄位：timestamp、level、event、request_id、run_id、route、stage、duration_ms、outcome、error_type、http_status、driver、attempt、timeout_ms、fallback、input_count、output_bytes。
  5. **禁止記錄**：信件主旨／內文、地址、target、prompt、模型回答、API key、token、密碼、完整 exception body、CLI stderr。
  6. 將靜默 `continue` 改成 debug counter／warning event，只記錄 path hash 或 basename，不記錄內容。
  7. 增加 process-local counters 與 latency histogram，供 `/api/health` 或本機診斷端點讀取；health 檢查不得同步呼叫外部服務。
- **驗證方式**：
  1. 使用 `FAKE_VALUE_FOR_TEST` 模擬錯誤，執行後以 caplog 檢查事件存在。
  2. 掃描 captured logs，確認 `FAKE_VALUE_FOR_TEST`、prompt、內容欄位均未出現。
  3. 產生 20 個並行 request，確認各自 request ID 不同且可追到最終事件。
  4. 強制一個 JSON 解析錯誤，確認有 warning 與 counter，而非完全靜默。
- **優先級**：**P1**
- **完成定義**：任何 production-like failure 都可由本機結構化日誌定位到 request、階段、時間與安全錯誤類型，且不記錄敏感內容。

## PRF-10：為 deliverable 建立 metadata index、分頁與保留策略

- **分類**：效能、磁碟資源洩漏
- **判定**：已確認。
- **位置**：`server/features/agents.py`：`save_deliverable()`、`list_deliverables()`、`read_deliverable()`。
- **證據**：
  - `list_deliverables(limit)` 仍會讀取並解析目錄內所有 JSON，完成排序後才切片。
  - `limit` 只減少回傳數量，不減少磁碟 I/O。
  - 同一內容保存為 MD、HTML 與 JSON 三份，沒有 prune 或 archive 流程。
  - 每次 task 都可建立新 deliverable，沒有總量上限。
- **影響**：
  - 目錄越大，每次開啟成果列表都越慢。
  - JSON 解析完整 card body，記憶體與 GC 壓力隨全部歷史內容成長。
  - 三份重複內容使磁碟成長約為內容量的數倍，且無回收路徑。
- **建議修法**：
  1. 以 SQLite metadata table 保存 id、title、kind、created、driver、fallback、path、size、revision；list 只查 index，不再掃目錄。
  2. canonical content 只保存一份；HTML 可按需產生並快取，MD 作為可攜式 export projection。
  3. 以 keyset pagination（created + id）取代 offset；回應包含 `next_cursor`。
  4. 預設先加「soft quota」與 UI 警告，不在未告知使用者時自動刪除成果；清理必須明確、可預覽、可確認。
  5. 若 BOB 核准自動保留政策，再以天數與數量雙上限執行；刪除 metadata 與 projection 必須一致。
  6. 提供 repair command／endpoint 找出無 metadata、metadata 無檔案及 checksum 不符項目。
- **驗證方式**：
  1. 建立 10,000 個 fake metadata 記錄，量測 list 只讀 page size 附近資料。
  2. 驗證 cursor pagination 不重複、不遺漏，同時段以 id 作 tie-breaker。
  3. 模擬刪除其中一種 projection，確認 repair 能指出不一致。
  4. 啟用核准的保留策略後，確認磁碟用量回到上限內且 index 不留孤兒列。
- **優先級**：**P1**
- **完成定義**：成果列表成本由全歷史大小降至單頁大小；內容只保存一份；所有清理都可追蹤且不會無提示刪資料。

## PRF-11：將 Second Brain 搜尋改為增量索引

- **分類**：效能、擴充性
- **判定**：已確認。
- **位置**：`server/second_brain.py`：`load()`、`search()`、`add_card()`、`rebuild()`。
- **證據**：`search()` 讀取完整 index，對每張卡片建立 lowercase blob 後做 substring 搜尋，複雜度為 O(N)。
- **影響**：
  - 卡片數增加後，每個搜尋都需讀取全部 body 並建立大量暫時字串。
  - API 延遲與尖峰記憶體會隨歷史總量成長。
- **建議修法**：
  1. 優先沿用 repo 已採用的 SQLite FTS5 模式，建立 title/body FTS table。
  2. 每次 card 新增、更新、刪除時同步更新索引；不要在每次搜尋前全量重建。
  3. SQLite 無 FTS5 時保留 LIKE fallback，但加上總行數、時間窗與成本上限，並暴露 `engine`。
  4. metadata index 不再包含完整 body；只保留搜尋引擎 reference。
- **驗證方式**：
  1. 建立 50,000 張純假卡片，量測冷啟動與 p95 查詢時間。
  2. 搜尋建議驗收目標：一般本機 SSD 上 p95 小於 200 ms；若環境較慢，至少要證明不再隨 N 線性增長。
  3. 新增、更新、刪除卡片後立即查詢，確認索引一致。
  4. 停用 FTS5 時確認 fallback 仍正確回報 engine 與限制。
- **優先級**：**P2**
- **完成定義**：搜尋成本由卡片總量線性成長改為索引驅動；更新與刪除保持一致。

## PRF-12：將 persona 從 request-time 完整重建改為快取與增量失效

- **分類**：效能、併發
- **判定**：已確認。
- **位置**：`server/persona.py`：`load()`、`rebuild()`；`server/features/email_brain.py`：修正保存後的 rebuild hook 需一併核對。
- **證據**：persona 檔不存在時，`load()` 會同步呼叫 `rebuild()`；`rebuild()` 會掃描最多 200 封信並建立看板。
- **影響**：
  - 冷啟動或檔案遺失時，第一個請求承擔完整成本。
  - 多個並行請求會同時啟動昂貴 rebuild，形成 thundering herd。
- **建議修法**：
  1. 啟動時預熱 persona；request path 只讀已驗證 cache。
  2. 以 sync watermark、email count 或 revision 判斷是否過期。
  3. 需要更新時由單一 worker 增量重建，再原子發布新 revision。
  4. 若檔案不存在，回明確的 temporary unavailable 或 deterministic fallback，不可讓所有並行 request 各自重建。
- **驗證方式**：
  1. 冷啟動並行 100 requests，量測 rebuild 實際執行次數，應為 1。
  2. 修改一封郵件後，確認只做增量失效，不掃描完整歷史。
  3. 強制 rebuild 失敗，確認舊 revision 繼續服務。
- **優先級**：**P2**
- **完成定義**：request path 不執行完整 persona 掃描；並行 cold start 只觸發一次重建。

## PRF-13：建立 Agent context 的位元組／token budget

- **分類**：效能、成本、可靠性
- **判定**：可見組裝層確認；`context_pack()` 內容量尚待驗證。
- **位置**：`server/features/agents.py`：`build_pack()`、`_local_sources()`；`server/agent_bridge.py`：`context_pack()`。
- **證據**：
  - `build_pack()` 同時載入 context pack、persona、brain 與最多 8 個 local sources。
  - 可見層沒有總 byte／token budget、去重規則或 context part 大小上限。
  - `_local_sources()` 依 target 查詢信件；若底層使用未索引 LIKE，成本可能隨資料量上升。
- **影響**：
  - 模型延遲、費用與記憶體可能隨 context 增大。
  - 同一信件可能同時存在於 recent mail、brain 與 sources，造成 context 膨脹。
  - 搜尋若掃描過多欄位，會增加本地 I/O。
- **建議修法**：
  1. 定義每個 part 與總體的 byte／token budget；以較小者為上限。
  2. local sources 優先走既有 FTS／索引欄位，限制掃描列數與 snippet bytes。
  3. 以 message id、thread id、content hash 做 context 去重。
  4. 超長 brain／persona 採摘要＋可追溯 reference，不直接無限展開。
  5. 在送出前記錄各 part 的 size count，但不記錄內容。
- **驗證方式**：
  1. fake driver 接收 context，驗證總大小不超過設定 budget。
  2. 建立大量重複信件，確認 context 去重有效。
  3. 對長本文建立上限，確認只截斷指定 part 且回應標示來源仍完整。
- **優先級**：**P2**
- **完成定義**：Agent context 大小有明確上限，且本地搜尋與送出成本不會隨完整信箱歷史線性成長。

## PRF-14：修正 UI 非同步回應 race 與 HTTP 錯誤處理

- **分類**：競態、UI 可靠性
- **判定**：已確認。
- **位置**：`ui/modules/agents.js`：`getJSON()`、`postJSON()`、`renderPane()`、`loadCards()`、`runTask()`、`runMention()`。
- **證據**：
  - `getJSON()` 未檢查 `response.ok`。
  - `renderPane()` 在 `await loadCards()` 後才檢查 view；多個載入可交錯。
  - 沒有 request generation token 或 AbortController，舊回應可能覆蓋較新的 cards／result 狀態。
- **影響**：
  - 使用者快速切換 kind、tab 或 view 時，可能看到舊任務或舊卡片。
  - 非 JSON 500 會拋出不明 parse error，UI 訊息不準確。
  - 已離開 view 的請求仍繼續佔用頻寬與 server 工作。
- **建議修法**：
  1. 每個 fetch 檢查 `response.ok`，再安全解析 JSON。
  2. 為 view、cards list、task 與 preview 分別建立 AbortController；新請求取消同類舊請求。
  3. 使用單調遞增 generation token；await 後只有 token 仍為最新且 view 條件相符才可 commit 狀態。
  4. UI 顯示固定錯誤類型與 retry action，不直接呈現可能含內部細節的 message。
- **驗證方式**：
  1. 以 deferred Promise 人工控制兩個 cards 回應逆序完成，確認舊回應不覆蓋新狀態。
  2. 切換 view 後完成舊請求，確認不更新新 view。
  3. fake server 回 500 非 JSON，確認顯示可理解的錯誤而非 JSON parse error。
- **優先級**：**P2**
- **完成定義**：任何晚到回應都不能覆蓋較新的 UI 狀態；離開 view 的請求會被取消。

## PRF-15：建立 usage JSONL 與排程日誌的輪替策略

- **分類**：資源洩漏、可觀測性
- **判定**：README 與 overnight 範例可證實檔案型記錄存在；`server/features/usage.py` 內文待確認。
- **位置**：
  - `server/features/usage.py`：README 描述模型呼叫會附加到 `data/usage.jsonl`
  - `scripts/overnight.py`：cron 範例將輸出附加到 `data/overnight.log`
- **證據**：文件未描述 rotation、壓縮、保留期限或總量上限；JSONL 每次模型呼叫都會增加。
- **影響**：
  - log 檔會無限增長。
  - 若以整檔讀取統計，啟動與用量頁面成本會持續上升。
  - 若多 writer 直接 append，需確認不會產生 partial line 或交錯紀錄。
- **建議修法**：
  1. 首選把 usage 事件寫入 SQLite，再輸出每日／每月 aggregate；JSONL 僅作可輪替 export。
  2. 若保留 JSONL，使用單一 append lock 或單 writer、`O_APPEND`、一事件一行與 fsync 策略；讀取時忽略並回報最後一個损坏行。
  3. 依大小與日期雙條件輪替；預設保留 90 天可由 BOB 調整。
  4. cron 使用系統 log rotation 或受控 logger，不直接無限制 append。
  5. 不記錄 prompt、回答、地址或憑證，只保留 token count、driver、估算標記與時間。
- **驗證方式**：
  1. 產生大量純假 usage events，確認每行可獨立解析且順序欄位合理。
  2. 啟用多 writer，確認沒有 partial line。
  3. 輪替後確認總磁碟維持在上限內，舊檔按政策保留。
- **優先級**：**P2**
- **完成定義**：usage 與排程日誌有可驗證的磁碟上限，且查詢不需載入完整歷史 JSONL。

## PRF-16：為 overnight 增加逐階段 deadline、時間與安全錯誤分類

- **分類**：逾時、可觀測性、錯誤恢復
- **判定**：已確認。
- **位置**：`scripts/overnight.py`：`main()`；`server/features/overnight.py`：`run()` 與各 stage。
- **證據**：目前主要輸出總 summary 與 errors list，沒有每階段 duration、開始／結束事件、剩餘 deadline 或標準化錯誤類別。
- **影響**：
  - 無法判斷 overnight 慢在 sync、triage、rules、drafts 或 brief。
  - 單一錯誤只出現在最後列表，難以判斷是否可安全重跑。
  - 總流程沒有 timeout 時可能被單一外部 driver 拖住。
- **建議修法**：
  1. 將流程拆成明確 stage，每階段記錄 `duration_ms`、outcome、safe error type、input/output count。
  2. 每階段使用剩餘 deadline；逾時後停止啟動新階段，已完成結果仍以 partial run 保存。
  3. 對每個外部 driver 設子 deadline，並記錄是否 timeout。
  4. 產生 machine-readable run manifest，但只包含統計與安全分類，不含信件內容。
  5. 定義 exit code：成功、部分成功、已有執行中、設定／資料錯誤。
- **驗證方式**：
  1. 在本機 fake driver 分別注入 timeout、5xx、invalid response。
  2. 確認每個 stage 都有單一開始與結束事件，且總時間不超過 deadline 加裕裕。
  3. 確認 partial run 不會被誤標為完整成功。
- **優先級**：**P2**
- **完成定義**：每個 overnight run 都能回答「哪個階段、多久、結果、何時可安全重跑」。

## PRF-17：強化 smoke harness 的 timeout、readiness 與診斷保留

- **分類**：測試可靠性、資源
- **判定**：scripts 層部分確認；workflow 是否已有 readiness 尚待核對。
- **位置**：`scripts/smoke.sh`；`.github/workflows/smoke.yml`（本輪不得修改）。
- **證據**：
  - `scripts/smoke.sh` 會解析並執行 workflow 的 `run:` steps，但沒有通用 per-step timeout。
  - background step 啟動後，script 本身沒有通用 readiness probe；若 workflow 未提供等待步驟，可能發生啟動 race。
  - 失敗時只印 server log 最後 40 行。
- **影響**：
  - CI 可能因無回應的 server 或 curl 而無限等待。
  - 啟動較慢時可能出現 flaky failure。
  - 失敗診斷被截斷，增加除錯時間。
- **建議修法**：
  1. 在 smoke harness 為每個 foreground step 設定合理 timeout；逾時時輸出 stage 名稱與安全摘要。
  2. background server 啟動後以 `/api/health` 做有上限的 readiness polling；不得對正式服務發送請求。
  3. 保留完整 server log，另印最後 40 行摘要；不得記錄敏感內容。
  4. 檢查 workflow 已有 curl retry／timeout，避免重複且保持行為一致。
  5. 修正 port 檢查與 bind 之間的 TOCTOU 機率；至少在失敗訊息清楚指出 port race。
- **驗證方式**：
  1. 在拋棄式本機副本注入一個會停滯的步驟，確認 harness 在期限內失敗並清理 server。
  2. 模擬 server 延遲啟動，確認 readiness probe 會等待而非立即誤判。
  3. 確認失敗後沒有殘留 process group。
- **優先級**：**P2**
- **完成定義**：smoke 不會無限等待，啟動 race 可重現消除，失敗時保留足夠診斷且不洩漏資料。

---

## 6. 發布前必做核心檔案驗證閘門

## PRF-G01：驗證 SQLite 連線、交易、索引與 busy timeout

- **分類**：併發、資料完整性
- **位置**：`server/yhbmail.py`：DB 初始化、`list_emails()`、sync／upsert、`counts()`；所有呼叫 SQLite 的 feature。
- **需要確認**：
  1. 是否每次 request／thread 使用獨立 connection，或有正確的 thread-local 管理。
  2. `sqlite3.connect()` 是否有合理 `timeout`；是否設定 `busy_timeout`、WAL 與合理 synchronous mode。
  3. 是否在持有 write transaction 時進行 IMAP／CLI／HTTP 網路等待；這會長期阻塞其他 writer。
  4. 所有 multi-step write 是否在同一 transaction；upsert 是否冪等。
  5. 高頻 query 欄位是否有索引；FTS 同步是否具交易一致性。
  6. connection、cursor 與 statement 是否在所有 exception path 關閉。
- **影響**：資料庫 locked、寫入遺失、長 transaction、FD 累積或同步重複寫入。
- **建議修法**：依驗證結果採 per-request connection、short transaction、bounded busy timeout、冪等 upsert 與必要索引；不得以無限期重試掩蓋 transaction 邊界錯誤。
- **驗證方式**：以暫存資料庫跑 20 readers、5 writers 的 barrier 測試；再注入 process crash，確認 DB 可恢復且無 partial logical state。
- **優先級**：**P1（驗證閘門）**
- **完成定義**：證明所有寫入路徑具 transaction 邊界、bounded lock wait 與冪等性，或另立具體修正項。

## PRF-G02：驗證 Agent bridge 的 timeout、response cap 與 CLI process cleanup

- **分類**：逾時、資源洩漏、憑證保護
- **位置**：`server/agent_bridge.py`：`_openai()`、`_cli()`、`_http()`、`load_agent_cfg()`。
- **需要確認**：
  1. 三種 driver 是否都強制 connect/read/total timeout。
  2. HTTP response 是否限制 bytes，錯誤 body 是否可能被回傳或記錄。
  3. CLI 是否在 timeout／client disconnect 後終止整個 process group，而非只關 parent。
  4. stdin 是否在 child 不讀取時及時關閉，避免 parent pipe 阻塞。
  5. API key 是否只由環境變數讀取，且不進 argv、錯誤或日誌。
  6. HTTP status、invalid JSON、empty response 是否已有 typed error。
- **影響**：永久停滯、孤兒 child、FD／pipe 洩漏、response 過大、敏感資訊進入 argv 或日誌。
- **建議修法**：若缺漏，依 PRF-01／07／08 的統一介面修正；driver 只負責 transport，feature 層負責總 deadline 與 outcome。
- **驗證方式**：使用本機假 HTTP／CLI server，覆蓋 timeout、慢 body、巨大 body、空 body、非 JSON、child 不讀 stdin。
- **優先級**：**P1（驗證閘門）**
- **完成定義**：三種 driver 都符合相同 deadline、大小、清理與錯誤契約。

## PRF-G03：驗證 IMAP timeout、session 清理與 body 上限

- **分類**：資源洩漏、逾時
- **位置**：`server/features/imap.py`：login、EXAMINE、UID SEARCH／FETCH、logout／close 路徑。
- **需要確認**：
  1. socket connect／read timeout 是否明確存在。
  2. 所有例外路徑是否在 `finally` 執行 `LOGOUT`／`close`，且 logout 失敗不遮蔽原始錯誤。
  3. UID FETCH 是否分批，是否有單封信、單帳號與總 bytes 上限。
  4. 重試是否只發生在可安全重試的讀取操作，且有 backoff 與總 deadline。
  5. 單一帳號失敗是否隔離，不阻止其他帳號。
- **影響**：IMAP socket 永久佔用、帳號鎖住、server thread 被拖死、下載量無界。
- **建議修法**：使用 per-operation timeout、`finally` 清理、分批 fetch、body cap 與 account-scoped circuit breaker。
- **驗證方式**：沿用 repo 既有本機假 IMAP 測試，額外模擬 server 在 SEARCH／FETCH／LOGOUT 前中斷；不得連正式 IMAP。
- **優先級**：**P1（驗證閘門）**
- **完成定義**：所有中斷點都會釋放 socket，單一帳號錯誤不影響其他帳號。

## PRF-G04：驗證 mail sync 的冪等、checkpoint 與部分失敗隔離

- **分類**：競態、錯誤恢復
- **位置**：`server/yhbmail.py`：`sync_all()` 及各 driver dispatch；`server/features/imap.py`。
- **需要確認**：
  1. 同一帳號重複 sync 是否只 upsert、不重複建立信件。
  2. 每個帳號是否有獨立 checkpoint，失敗後重跑是否從安全點繼續。
  3. 網路下載與 DB transaction 是否分離，避免長時間持鎖。
  4. 多帳號是循序或並行；若並行，是否有總 deadline 與 bounded concurrency。
  5. 一個 driver crash 是否會中止全部帳號，或只記錄該帳號錯誤。
- **影響**：重複信件、資料庫長時間鎖住、同步卡死或單一帳號拖垮全部同步。
- **建議修法**：以 account + remote uid／message id 做冪等 key；先取得並正規化資料，再開短 DB transaction 寫入；每帳號獨立錯誤與 checkpoint。
- **驗證方式**：使用本機假 drivers 注入重複資料、timeout、半途失敗與同帳號並行 sync，確認無重複且其他帳號可完成。
- **優先級**：**P1（驗證閘門）**
- **完成定義**：重跑 sync 不產生重複資料；單一帳號失敗可隔離並安全重試。

## PRF-G05：驗證 HTTP server request 生命週期與 body 上限

- **分類**：併發、資源、DoS 防禦
- **位置**：`server/app.py`：server 建立、request 讀取、handler dispatch、response、shutdown。
- **需要確認**：
  1. 使用單一 thread、thread-per-request 或其他模型；thread 是否有上限。
  2. `Content-Length` 與 chunked body 是否在完整解析前設 hard limit。
  3. client disconnect 時 feature job 是否能收到 cancellation。
  4. access log 是否含 request ID、route、status、duration，且不記錄 body。
  5. SIGTERM／SIGINT 是否能停止 accept loop、等待有限時間並關閉 DB／child。
  6. health endpoint 是否保持快速且不依賴外部服務。
- **影響**：大量本機請求耗盡 thread／記憶體；慢 body 佔用連線；關機留下孤兒工作。
- **建議修法**：若使用 thread-per-request，加入 bounded executor；所有 request body 設上限；傳遞 deadline／disconnect；實作有限時 graceful shutdown。
- **驗證方式**：本機啟動 server，使用大量半開 body、慢 request 與並行 health check；再送 SIGTERM，確認 port 與 child 都釋放。
- **優先級**：**P1（驗證閘門）**
- **完成定義**：request 數量、body 大小與 thread 數量都有上限；server 可有限時間停止。

## PRF-G06：驗證 cache clear、規則與設定檔的並行一致性

- **分類**：競態、錯誤恢復
- **位置**：
  - `server/features/cache.py`：cache clear／reseed
  - `server/features/rules.py`：規則讀寫
  - `server/features/mailops.py`：accounts、signature 等 JSON 設定
  - `server/features/plugins.py`：feature 載入狀態
- **需要確認**：
  1. clear／reseed 是否會和同步、搜尋索引或 Agent task 同時發生。
  2. 設定檔是否採 atomic replace 與 lock；是否可能暫時變成空檔。
  3. 寫入失敗是否保留舊版本，並回報明確錯誤。
  4. cache clear 是否清理衍生 index／cards，而非只清 DB。
  5. feature import error 是否只記錄一次且不影響其他 feature。
- **影響**：設定遺失、cache 半清、索引與 DB 不一致、故障後每次 request 重複嘗試 import。
- **建議修法**：以 DB transaction／版本化 generation 管理 clear；所有 JSON 採 atomic replace；cache clear 發布 generation，衍生重建只在完成後切換。
- **驗證方式**：並行執行 clear、sync、Agent task、規則更新，並在每個寫入點注入例外；確認舊或新完整版本至少有一套可用。
- **優先級**：**P2（驗證閘門）**
- **完成定義**：任何並行組合都不會留下部分設定、孤立索引或不可恢復的 cache 狀態。

---

## 7. 建議实施顺序

### Phase 0：建立可觀測基線

1. 加入 request ID／run ID 與安全結構化事件。
2. 記錄 endpoint、stage、duration、outcome、error type，不記錄內容。
3. 加入 process-local counters，確認目前最慢路徑與實際 concurrency。
4. 以本機 fake services 建立 timeout、slow response、failure baseline。

**退出條件**：能在不接正式服務的情況下回答每次請求的耗時、錯誤與 fallback 狀態。

### Phase 1：先消除 P1 正確性與可用性風險

1. PRF-01：統一 deadline 與 cancellation。
2. PRF-02：server-side concurrency／queue／idempotency guard。
3. PRF-03：overnight single-flight lock。
4. PRF-04、PRF-05、PRF-06：atomic publish、lock、transaction、recovery。
5. PRF-07：輸入與輸出大小上限。
6. PRF-08：typed error、retry policy 與 circuit breaker。
7. 完成 PRF-G01～PRF-G05 的原始碼驗證，發現問題即另開修正項。

**退出條件**：所有 P1 測試通過；故障注入後沒有半檔、孤兒 process、重複計費或永久停滯。

### Phase 2：控制資源成長

1. PRF-10：deliverable metadata index、分頁與 soft quota。
2. PRF-11：Second Brain FTS／增量索引。
3. PRF-12：persona cache 與增量失效。
4. PRF-15：usage／log rotation。
5. 完成 PRF-G06。

**退出條件**：10,000／50,000 筆 fake dataset 下，清單與搜尋成本符合驗收目標；磁碟用量有明確界線。

### Phase 3：強化前端與背景流程

1. PRF-13：context budget 與去重。
2. PRF-14：UI AbortController 與 generation token。
3. PRF-16：overnight stage observability。
4. PRF-17：smoke timeout／readiness。

**退出條件**：晚到回應不污染新狀態；background run 與 CI 均可預測地結束並提供診斷。

---

## 8. 建議 observability 契約

### 8.1 必要事件

| 事件 | 必要欄位 | 用途 |
|---|---|---|
| `http.request.finish` | request_id、route、method、status、duration_ms | API 延遲與錯誤率 |
| `agent.run.finish` | request_id、driver、attempt、outcome、duration_ms、fallback、output_bytes | 模型呼叫與降級 |
| `agent.retry` | request_id、attempt、error_type、backoff_ms | 重試與上游健康 |
| `deliverable.publish` | deliverable_id、bytes、duration_ms | 寫入失敗與大小 |
| `persona.rebuild` | revision、duration_ms、outcome、source_count | 冷啟動與重建成本 |
| `brain.rebuild` | revision、card_count、removed_count、duration_ms | index／projection 一致性 |
| `sync.account.finish` | account_key、driver、fetched_count、stored_count、outcome、duration_ms | 單帳號同步隔離 |
| `overnight.stage` | run_id、stage、outcome、duration_ms、error_type | 夜班流程定位 |

### 8.2 明確禁止欄位

- 郵件主旨、內文、snippet、地址、thread subject
- Agent target、prompt、模型回答
- API key、token、password、cookie、authorization header
- IMAP／CLI 完整 stderr
- 未遮蔽的 exception response body

### 8.3 本機指標建議

- request count、status code、duration histogram
- active／queued／rejected agent calls
- agent outcome、retry count、fallback count
- SQLite busy／transaction retry count
- sync fetched／stored／duplicate count
- deliverable count、total bytes、largest bytes
- orphan projection／corrupt metadata count
- overnight stage duration、partial-run count
- child process／open FD baseline（僅診斷工具）

這些指標可保留在本機 process、SQLite 或本機 log，不需要外部 telemetry。

---

## 9. 驗證策略

### 9.1 測試原則

1. 只使用標準函式庫既有測試框架。
2. 所有暫存資料使用 `tempfile.TemporaryDirectory()` 或測試框架提供的 tmp path。
3. 測試不得寫入 repo 實際的 `data/`、`vault/`、真實帳號設定或正式服務。
4. 所有假憑證與假內容使用 `FAKE_VALUE_FOR_TEST`。
5. 本機 HTTP／IMAP 測試只綁 `127.0.0.1` 與 ephemeral port。
6. 不把假信件內文放入 assertion log，除非是驗證「不應被記錄」的負向測試。

### 9.2 建議新增的測試群組

#### Timeout／retry

- connect timeout
- read timeout
- total deadline
- HTTP 429 + Retry-After
- HTTP 5xx 後成功
- 4xx 不重試
- 已送達但結果不明時不重複計費呼叫
- timeout 後 child process 已清理

#### Concurrency／race

- 20 個並行 Agent task 不超過 active limit
- queue 滿回 429
- 兩個 overnight run 只有一个進入核心流程
- 50 個並行 persona load 只重建一次
- 100 個並行 Second Brain add 不丟資料
- 50 個並行 deliverable publish 均可完整讀取

#### Fault injection

- temp write 前失敗
- temp write 後、replace 前失敗
- JSON 寫入一半失敗
- index replace 失敗
- lock owner 被終止
- SQLite busy／commit 失敗
- cache clear 與 sync 同時發生

#### Scale

- 10,000 個 deliverable metadata
- 50,000 個 Second Brain fake cards
- 200 封 fake emails 的 persona rebuild
- 大量 context 與重複信件
- 大量 usage events 與 log rotation

#### Observability／privacy

- 每個 request 有 request ID
- 每個 outcome 有且只有一個安全分類
- fallback 原因可辨識
- log 不含 `FAKE_VALUE_FOR_TEST` 與其他禁止欄位
- error body 不進 response 或 log

### 9.3 建議執行順序

```bash
python3 -m unittest discover -s tests -v
bash scripts/smoke.sh
```

本輪是文件-only，未實際執行上述命令。實作每個 P1 項目時，應先加入對應失敗測試，再修改程式；不得只以 smoke 通過取代 race、fault injection 與 scale 測試。

---

## 10. 建議驗收指標

以下是起始驗收目標，不是目前實測值：

| 指標 | 驗收目標 |
|---|---|
| Agent 總 deadline | 單次不超過設定 deadline 加 2 秒 |
| 超時後 child／socket | 0 個遺留 |
| Agent active 上限 | 預設最多 2 個外部呼叫 |
| DB locked 壓力測試 | 0 次未處理 `database is locked` |
| Persona 併行 cold start | 只執行 1 次 rebuild |
| Second Brain 100 個並行新增 | 0 個 lost update |
| Deliverable list I/O | 只讀 metadata page，不讀完整歷史內容 |
| Second Brain 搜尋 | 50,000 張 fake cards 下 p95 建議低於 200 ms |
| UI 晚到回應 | 不覆蓋新 view 狀態 |
| Overnight 重疊 | 同時只有 1 個有效 run |
| 資源用量檔 | 有 rotation／retention，磁碟不無限增長 |
| 敏感資料日誌 | 0 筆 prompt、內容、地址、token 或憑證 |
| 原子寫入故障注入 | 不公開任何半檔或不一致版本 |

---

## 11. 決策記錄

本次採用的保守決策如下：

1. **維持 local-first 與零外部 telemetry**：觀測資料只留本機。
2. **維持 Python 標準函式庫限制**：不因本報告新增 pip 相依。
3. **不自動刪除使用者可見成果**：deliverable 先做 index、配額提示與明確 purge；自動保留期限需 BOB 核准後才啟用。
4. **不對可能計費且沒有 idempotency 的 Agent 呼叫盲目重試**：只重試可確認未受理的 transient error。
5. **所有共享狀態變更採 lock 與 atomic publish**：優先使用既有 SQLite 與標準函式庫。
6. **保留既有 MD／HTML 匯出相容性**：先消除三份內容的同步管理與全目錄掃描，再考慮改成單一 canonical format。
7. **overnight 採 single-flight**：重疊執行不排隊累積，而是明確拒絕新 run。
8. **本輪不修改 workflow 或既有程式**：核心檔案缺少內容的部分以驗證閘門列出，不做臆測性修改。

---

## 12. 需要 BOB 決策的事

下列項目有合理的預設建議，但會影響資料保存、成本或本機資源使用政策：

1. **Deliverable 保留政策**：建議先「500 張或 90 天 soft quota + 明確 purge」；若改為自動刪除，需確認可接受。
2. **Usage／overnight log 保留期**：建議 90 天；高流量環境可縮短或改以每日 aggregate 為主。
3. **Agent timeout 與併發預設**：建議 connect 5 秒、read 60 秒、總計 120 秒、active 最多 2、queue 最多 8。
4. **Overnight 總期限與帳號子期限**：建議總計 15 分鐘、單帳號 60 秒；大型帳號可能需另設 per-account override。
5. **Second Brain 儲存遷移**：短期先 atomic index，之後是否正式遷移至 SQLite FTS5，會影響檔案相容性。
6. **是否保留可攜式 MD／HTML 匯出**：若只保留 SQLite，可顯著降低磁碟與一致性成本；若要繼續直接編輯 Markdown，則需保留 projection 同步機制。
7. **正式服務連線驗證的授權邊界**：本報告只要求本機 fake service；若後續要做真實 mailbox／model timing benchmark，需另行明確授權，且不得記錄真實內容。
