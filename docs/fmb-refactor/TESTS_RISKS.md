# 需先補的測試、風險與決策

所有測試只使用 `tempfile`／`tmp_path`、`fixtures/` 既有虛構資料，以及 `FAKE_VALUE_FOR_TEST` 這類明顯假字串。不得連線外部服務、不得讀寫 repo 外路徑、不得寫入真實憑證。

## 1. B0：characterization 測試（動刀前必備）

測試檔名依 repo 慣例 `tests/test_tpi_*.py`。可擴充既有檔（`test_tpi_agents_core.py`、`test_tpi_agents_mention.py`、`test_tpi_agents_ui.py`）或新增；新增時建議：

| 新檔 | 覆蓋 |
|---|---|
| `tests/test_tpi_agents_deliverables.py` | 儲存層 roundtrip、id 規則、路徑安全、HTML 轉義 |
| `tests/test_tpi_agents_contract.py` | HTTP 回應鍵集合與狀態碼凍結 |
| `tests/test_tpi_agents_locale.py` | 語言代碼與文案選擇 |

### 1.1 `parse_mention()`（純函式，最高價值）

| 案例 | 輸入 | 期望 |
|---|---|---|
| 裸提及 | `@agent` | `kind=research_person`、`target=""` |
| 帶對象 | `@research Samira Ortiz 最近往來` | `kind=research_person`、`target` 為 `Samira Ortiz 最近往來` 去請求詞後的字串 |
| 連字號別名 | `@research-company Northwind` | `kind=research_company` |
| 大小寫 | `@AGENT 會議準備` | 有觸發，`word="agent"` |
| 句中出現 | `請看 @prep 週四會議` | 有觸發，`kind=meeting_prep` |
| 無提及 | `hello team` | `None` |
| 前綴黏著 | `x@agent` | `None`（`(?<![\w.])` 生效） |
| 超長 | 5000 字 | 不拋錯，內部截到 `MAX_BODY` |
| 多行 | `@agent A\n第二行 B` | `target` 只取同一行 |

### 1.2 儲存層

- `save → list → read`：三格式（md／html／json）都存在且可讀回；`list` 回傳的 metadata 鍵集合固定。
- 非法 id：`""`、`"a"`、`"../etc/passwd"`、`"ABC"`、`"x"*81`、`"a b"` → `read` 回 `None`，且不建立任何路徑。
- 非法 fmt：`"exe"`、`"MD"` → `None`。
- 目標字串：空字串、純中文、純標點、200 字 → `make_id()` 產出值必符合 id 規則（此案例在 B3 前先以「現況允許的行為」寫，B3 後仍須綠）。
- HTML 轉義：內文含 `<script>alert(1)</script>`、`"`、`&`、`<img onerror=x>` → 輸出不含未轉義的 `<script`、` onerror=`；`<title>` 內亦同。

### 1.3 HTTP 契約

- `POST /api/agents/task`：`kind` 非法 → 400 且含 `kinds`；`target` 與 `ask` 皆空 → 400；成功時鍵集合為 `{"deliverable","text","driver","fallback","error","sources"}`。
- `POST /api/agents/mention`：`email_id` 不存在 → 404；非別名且無提及 → `{"triggered": false}` 且不寫入任何檔案；成功時鍵集合多加 `triggered`／`via`／`mention`。
- `GET /api/agents/deliverables`：`limit` 非法字串 → 退回 50；`limit` 超大 → 上限 200。
- `GET /api/agents/deliverables/<id>.<fmt>`：不存在的 id → 404；合法 id 但 fmt 非法 → 404。
- 非本機 Origin 的 POST → 拒絕（沿用 `_origin.refuse`）。

### 1.4 locale

- `/api/agents/*` 帶 `lang=zh-Hant`、`zh`、`en`、空字串 → 生成的卡片 `lang` 欄位分別為 `zh`／`zh`／`en`／`en`。
- `_local_brief()` 在 zh 與 en 下，標題與「本機啟發式」提示都存在於輸出中（子字串斷言，不做全文快照）。

### 1.5 守門測試（可選，B4 之後）

- `server/features/agents.py` 所有函式 < 60 行（用 `ast` 在測試內計算，讀檔範圍限 repo）。
- 同一測試可一併檢查 `ui/modules/agents.js` 內 `S.zh` 與 `S.en` 的鍵集合相等（以正則抓 `^\s{6}(\w+):`）。**注意**：此法對格式敏感；若嫌脆弱，改用人工清單並在 PR 描述附上，不納入 CI。

## 2. 各批需先補的測試

| 批次 | 新增／擴充 | 重點 |
|---|---|---|
| B1 | `test_tpi_agents_contract.py`（擴充） | `complete()` 的四種 driver 分支、失敗時 driver=local、error 不含訊息本文 |
| B2 | `test_tpi_agents_locale.py` | `zh`／`zh-Hant`／`zh_TW`／`ZH`／`en`／`""` 的判定與 pack 語言 |
| B3 | `test_tpi_agents_deliverables.py` | 路徑唯一入口、三格式 roundtrip、HTML 轉義、id 邊界 |
| B4 | 同上擴充 | `_result_payload` 鍵集合、`_mail_source` 兩種 snippet 來源、四種 `via` 分支 |
| B5 | `test_tpi_agents_ui.py`（擴充） | 深連結、thread 提及、預覽、語系切換；無 Node 時跳過語法檢查 |
| B6 | 各模組自身 UI 測試 | 遷移後每個模組仍可載入、nav 按鈕仍出現 |
| B7 | `test_fmb_docs_parity.py`（新） | 三組雙語文件的標題層級與互連連結一致 |

## 3. 風險

| 編號 | 風險 | 影響 | 緩解 |
|---|---|---|---|
| R1 | 既有測試以全文快照斷言 `_local_brief()` 或卡片 HTML | B3／B4 會紅 | B0 先確認；若存在，改為子字串斷言並在 PR 說明，不得刪除案例 |
| R2 | 回應 JSON 鍵順序或鍵名變動 | 前端或外部 Agent 讀不到 | B0 凍結鍵集合；`_result_payload` 保持鍵集合一致，不依賴順序 |
| R3 | `fallback=True` 但 `error=None` 的既有語意被「修正」 | 前端 fallback 標籤行為改變 | 保持既有語意，只收斂產生方式 |
| R4 | `error_label` 搬移後字串改變 | 前端顯示或測試比對失敗 | 先 `grep` 全 repo 使用點；只在 agents 路徑先切換 |
| R5 | 抽出 `_addr.py` 造成 `compose` 循環 import | 服務起不來 | 先讓 `_addr.py` 成為無依賴葉節點；`compose` 保留轉呼叫；以測試證明 import 圖無環 |
| R6 | 語言正規化放寬後，`zh_TW` 之類輸入改變行為 | 文案語言改變 | 只放寬「應判為中文」的輸入，不改英文判定 |
| R7 | `tag-` 前綴改名撞到既有 UI 測試或 CSS 選擇器 | UI 測試紅、樣式失效 | 同批同步改 CSS／HTML／測試；以 `grep -rn "tag-" ui/ tests/` 確認清零 |
| R8 | UI 模組 monkey-patch 在載入順序變動時靜默失效 | thread 內 @agent 消失 | B5 不動覆寫機制，只加註解與防護；載入順序留待 B6 評估 |
| R9 | B6 動到 `ui/index.html` loader | 所有模組可能一起失效 | 需 BOB 同意；一次只遷一個模組，可單檔回滾 |
| R10 | `fmb_feature2/` 若被搬進 `server/features/` 會自動註冊新路由 | 多出未審查的端點 | 保守預設：本計畫不動，只加註說明；接線另案處理 |
| R11 | 大範圍重整稀釋審查焦點 | 回歸風險上升 | 每批一個 PR、單一主題、行數上限（建議 < 300 行 diff） |
| R12 | 測試環境無 Node | UI 語法檢查被跳過 | 既有慣例已允許跳過；Python 核心測試不可依賴瀏覽器 |

## 4. 回滾策略

| 批次 | 回滾方式 |
|---|---|
| B0 | 刪除新增測試檔 |
| B1 | `run_task()` 還原直接呼叫私有函式；新介面可留 |
| B2 | `agents.py` 還原三元運算式；`_i18n.py`／`_addr.py` 無使用者時刪除 |
| B3 | 函式搬回 `agents.py`；`_deliverables.py` 刪除 |
| B4 | `agents.py` 單檔回滾 |
| B5 | `ui/modules/agents.js` 單檔回滾 |
| B6 | 逐模組回滾 |
| B7 | 刪除 parity 測試與文件註記 |

## 5. 決策點（未決前採保守預設）

| # | 決策 | 保守預設 | 需要 BOB 決定的事 |
|---|---|---|---|
| 1 | 是否允許改 `ui/index.html` 或模組載入器以支援共用 UI kit | 不做（B6 暫緩），只統一命名 | 是否接受為了消除 UI 重複而動核心載入器 |
| 2 | `fmb_feature2/` 去留 | 不動程式，只在文件註明「暫存區、不被主程式載入」 | 納入 `server/features/`（含新測試）／保留／移除 |
| 3 | 是否把 `_local_brief()` 文案改為表格驅動 | 做，但保留所有既有字串與空白 | 是否接受文案有極小標點差異（會影響全文快照式測試） |
| 4 | 是否把 agent 別名改成更明顯的假值 | 不改常數，改為由 API 曝光、UI 讀取 | 是否要換成 `agent@example.invalid` 之類更中性的值（屬行為變更，需獨立 PR） |
| 5 | 是否允許調整 `tests/` 內既有斷言 | 只允許放寬為子字串，不刪案例 | 是否接受刪除或改寫既有案例 |
| 6 | `triage.py`／`skills.py` 的 Agent 派送是否同批收斂 | 不同批，另立 B1b | 是否接受一次跨三個 feature 的較大改動 |
| 7 | 是否引入函式長度／i18n 鍵集合的 CI 守門 | 只做函式長度，i18n 檢查留人工 | CI 是否可增加此類靜態檢查 |

## 6. 明確不做的事

- 不新增寄信、排程寄送或遠端郵件寫入路徑。
- 不改 `.github/workflows`、secrets、憑證設定、git remote、分支。
- 不改資料庫 schema、fixtures、示範資料。
- 不引入 pip／npm 相依，不改 `install.sh`／`run.sh` 的行為。
- 不把 Python 外掛描述成沙箱，也不新增外掛隔離機制。
- 不為了「看起來整齊」而改動未經測試覆蓋的模組。
