# 分階段升級計畫

本計畫為建議稿，**不代表已經執行**。每個階段都只描述未來 PR 應進行的變更、相容性風險、驗證方式與回滾方式。實際修改產品碼、測試或 CI 前，需先完成對應決策點。

## 階段 0：基線盤點與凍結現況

### 目標

建立可重現的升級前基線，確認目前 repo 狀態、測試結果與環境版本。

### 變更

- 不修改產品碼、測試、CI、secrets、git 設定。
- 新增本 `docs/fmb-upgrade/` 文件。
- 在目標機執行 `inventory.md` 的量測指令，記錄到本地不提交的筆記。
- 記錄未提供的檔案狀態：`.github/workflows/smoke.yml`、`install.sh`、`scripts/smoke.sh` 內容需人工確認。

### 相容性風險

- 文件本身無執行期風險。
- 若量測指令誤寫入 repo 資料目錄，可能污染本機狀態；必須使用唯讀查詢或暫存路徑。

### 驗證方式

```bash
git status --short
python3 -m unittest discover -s tests
scripts/smoke.sh
bash -n run.sh install.sh scripts/smoke.sh
node --check ui/modules/*.js || true
```

- FTS5 探測：使用 `inventory.md` 的 Python 片段。
- 預期：只有 `docs/fmb-upgrade/` 新檔；核心測試與 smoke 不得因新增文件而失敗。

### 回滾方式

- 若文件或分支狀態有誤，直接捨棄本文件 commit；不影響產品碼或資料。

---

## 階段 1：更新 Python 版本政策

### 目標

把宣告的 Python 下限從 3.9 提高到 3.11，並定義測試矩陣 3.11–3.13。

### 變更（未來 PR）

- 更新 `README.md`、`README.zh-Hant.md`、`CONTRIBUTING.md`、`CONTRIBUTING.zh-Hant.md`。
- 更新 `docs/fmb/ARCHITECTURE.md` 的執行期必要相依表。
- 若 `install.sh` 有 3.9 版本檢查，更新為 3.11 下限；未確認前不得推測內容。
- 未來經 BOB 同意後，更新 `.github/workflows/smoke.yml` 的 Python 矩陣；本任務不修改。
- 不引入 pip 相依，不新增套件管理流程。

### 相容性風險

| 風險 | 影響 | 緩解 |
|---|---|---|
| 仍在使用 Python 3.9／3.10 的用戶無法啟動 | 可用性下降 | 文件明示最低版本與升級指引 |
| Python 3.12／3.13 移除或棄用舊 API | 執行期例外 | 先跑完整測試與靜態檢查 |
| install.sh 版本判斷寫法不佳 | 誤判或誤阻 | 以乾淨暫存環境測試 |
| CI 矩陣變多 | 時間與維護成本 | 先用 3.11 單版本，再擴 3.12／3.13 |

### 驗證方式

- 在 Python 3.11、3.12、3.13 分別執行：

```bash
python3 -m unittest discover -s tests
```

- 在暫存根目錄執行：

```bash
OPENINBOX_NO_BROWSER=1 OPENINBOX_PORT=18770 ./run.sh
```

- 確認 `install.sh` 版本檢查在 3.10 與 3.11 行為符合預期。

### 回滾方式

- 回復 README、CONTRIBUTING、ARCHITECTURE、install.sh 的版本字串。
- 若已改 CI，回復原矩陣。
- 本階段不涉及資料庫或快取，回滾不需還原本機資料。

---

## 階段 2：標準函式庫相容性強化

### 目標

在 Python 3.11–3.13 下移除或避開已棄用、已移除或行為不一致的標準函式庫用法，同時維持零 pip。

### 變更（未來 PR）

- 針對測試失敗項目做最小修正。
- 補上回歸測試，特別是 SQLite、時間處理、郵件包裝、HTTP、MCP、UI 模組載入。
- 不引入第三方套件、不新增託管服務、不新增遙測。

### 相容性風險

- SQLite 回傳值、例外類型或交易行為在不同 Python 建置下可能不同。
- FTS5 與 LIKE fallback 的搜尋結果可能不一致。
- 時區、日期格式、IMAP 編碼可能在跨版本下出現邊界差異。
- 例外訊息若直接包進回應，可能洩漏外部端點內容；必須維持只回報錯誤類別與 HTTP 狀態。

### 驗證方式

```bash
python3 -m unittest discover -s tests
scripts/smoke.sh
PYTHONPYCACHEPREFIX="$(mktemp -d)" python3 -m compileall -q server tests
```

- 使用假 IMAP、假 CLI、假 HTTP worker、假 MCP client 測試，不連正式服務。
- 需要假金鑰或假密碼時只用 `FAKE_VALUE_FOR_TEST`。

### 回滾方式

- 以單一 commit 形式回復相容性修正。
- 本階段原則上不改 schema；若意外涉及資料表，必須先完成階段 3 備份與還原流程。

---

## 階段 3：SQLite／FTS5 與本機資料相容性

### 目標

確保升級 Python 或 SQLite 時，本機郵件快取、搜尋索引、衍生卡片與人格資料不會毀損或長時間不一致。

### 變更（未來 PR）

- 明定 schema 版本檢查與遷移策略。
- 提供搜尋索引可重入重建流程。
- 提供資料庫一致性與數量檢查，不含郵件內文明文。
- 文件化備份、verify、restore dry-run 原則；完整備份功能可參考 `docs/fmb/ROADMAP.md` 第 1 項。
- 維持 FTS5 缺少時自動回落 LIKE。

### 相容性風險

| 風險 | 影響 | 緩解 |
|---|---|---|
| 直接複製正在寫入的 SQLite | 備份不一致 | 使用 SQLite backup API 或先停止服務 |
| 遷移寫壞 schema | 資料毀損 | 先 dry-run，再於暫存副本驗證 |
| FTS5 可用性改變 | 搜尋效能或結果差異 | 分別測試 FTS5 與 LIKE |
| 衍生資料過期 | 舊摘要、舊卡片被當現況 | 清理快取並驗證可重生 |
| 索引重建過慢 | UI 卡住 | 以暫存資料集量測，避免阻塞同步 |

### 驗證方式

- 在暫存根目錄建立假郵件資料，執行完整同步、搜尋、清除快取、重載示範。
- 比對 FTS5 與 LIKE 的搜尋結果集合。
- 執行資料庫備份與還原 dry-run：

```bash
python3 - <<'PY'
import pathlib, sqlite3, tempfile
src = pathlib.Path("data/openinbox.db")
if not src.exists():
    print("no local db; skip")
    raise SystemExit(0)
tmp = pathlib.Path(tempfile.gettempdir()) / "openinbox-upgrade-check.db"
with sqlite3.connect(src) as s, sqlite3.connect(tmp) as d:
    s.backup(d)
print("backup-ok", tmp)
PY
```

- 驗證 manifest 或數量檢查不回傳郵件主旨、寄件人、內文。

### 回滾方式

- 還原升級前備份到暫存根目錄，先驗證再覆蓋正式 `data/`。
- 回復遷移程式與索引重建程式。
- 若搜尋結果異常，關閉新索引流程，回到既有 FTS5／LIKE 路徑。

---

## 階段 4：PWA、瀏覽器與前端快取相容性

### 目標

確保 UI 模組在現代瀏覽器可運行，並避免升級後 service worker 提供過期腳本。

### 變更（未來 PR）

- 每次 UI 或 service worker 變更時提升快取版本。
- 明定 `ui/pwa/sw.js` 與 `ui/modules/*.js` 的快取清單檢驗。
- 若需要更舊瀏覽器支援，另立決策；不在本階段引入 npm build pipeline。
- 文件化支援的瀏覽器最低版本。

### 相容性風險

- 舊 Safari 或舊 Android WebView 不支援 optional chaining／nullish coalescing。
- Service worker 更新時序不當，使用者拿到舊 UI。
- 離線頁或 manifest 快取造成調試困難。
- `node --check` 只檢查語法，不檢查瀏覽器 API 相容性。

### 驗證方式

```bash
node --check ui/modules/agents.js
node --check ui/pwa/sw.js || true
```

- 在 Chrome、Edge、Firefox、Safari 手動或自動驗證：
  - 開啟面板。
  - 切換繁中／英文。
  - 重新整理後 UI 更新。
  - Service worker 更新後不再回舊模組。
- 確認 `/api/*` 不進 service worker cache。

### 回滾方式

- 回復 UI／service worker commit。
- 再次提升快取版本，迫使瀏覽器汰換舊快取。
- 不需還原伺服器資料庫；只需清理或覆寫 PWA 快取。

---

## 階段 5：MCP 與可選外部 Agent／郵件驅動契約

### 目標

在不升級正式外部服務的前提下，確保 MCP、Agent 驅動與郵件 CLI 的升級不會破壞本地合約。

### 變更（未來 PR）

- 補齊 MCP initialize、tools/list、tools/call、ping 與錯誤格式測試。
- 新工具或新能力必須可被舊客戶端忽略。
- 對 `openai_compatible`、`cli`、`http` 驅動建立逾時、錯誤正規化與本機 fallback 測試。
- 對 `gog`、`gsk`、IMAP 建立假驅動測試，不斷連正式服務。

### 相容性風險

| 風險 | 影響 | 緩解 |
|---|---|---|
| MCP 協定版本變動 | 舊客戶端無法初始化 | 維持 `2025-06-18` 相容，新增欄位可忽略 |
| 新工具回應過大 | 客戶端處理變慢 | 限制數量，使用本機索引 |
| CLI 輸出格式改變 | 解析錯誤或誤判 | 以假 CLI 測試錯誤類別 |
| OpenAI 相容 API 漂移 | Agent 呼叫失敗 | 回落本機啟發式並標示 fallback |
| 外部 Agent 資料外送 | 郵件或上下文離開本機 | 文件明示資料範圍，預設不啟用 |
| IMAP 伺服器行為差異 | 同步失敗或漏信 | 以 EXAMINE、BODY.PEEK 假測試維持唯讀 |

### 驗證方式

```bash
python3 -m unittest discover -s tests
```

- MCP 端對端測試使用 stdio 與假客戶端。
- CLI／HTTP 測試只使用 loopback fake worker。
- 需要假金鑰時使用 `FAKE_VALUE_FOR_TEST`。

### 回滾方式

- 回復 MCP 或驅動程式碼，保留舊工具與舊欄位。
- `agent.json`、`accounts.json` 不因回滾而被迫修改。
- 本機資料不需還原；外部服務從未升級。

---

## 階段 6：上線演練與文件收尾

### 目標

把前面階段整理成可重跑的升級 runbook，並演練回滾。

### 變更（未來 PR）

- 在 `docs/fmb-upgrade/` 補一份實際上線檢查表。
- 文件化支援矩陣、已知限制與回滾聯絡人。
- 不新增遙測；維運指標只記錄事件類型、錯誤類別、HTTP 狀態與耗時。

### 相容性風險

- 演練不完整導致正式升級時找不到回滾點。
- runbook 包含敏感資料或外部端點原始回應。

### 驗證方式

- 在暫存根目錄完整執行：
  1. 備份。
  2. 升級。
  3. 驗證。
  4. 回滾。
  5. 再次驗證。
- 確認文件無 token、金鑰、密碼、客戶個資、LINE 訊息內文或案件當事人資料。

### 回滾方式

- 回復至上一個穩定 commit。
- 必要時從備份還原 `data/` 與 `vault/`。
- 重新執行 smoke 與核心測試。
