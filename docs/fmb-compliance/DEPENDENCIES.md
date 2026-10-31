# 相依套件與授權相容性盤點

本文件盤點 openinbox 執行期與開發期的相依，判斷與本專案 MIT 授權的相容性，並列出散布義務與後續治理建議。

> 本文件不構成法律意見。授權條款的適用仍取決於實際散布方式（原始碼、容器映像、套件、SaaS）。

## 1. 專案自身授權

| 項目 | 內容 | 證據 |
|---|---|---|
| 授權 | MIT License | `[A]` `LICENSE` |
| 著作權標示 | `Copyright (c) 2026 TooPowerInbox contributors` | `[A]` |
| 第三方聲明檔 | 未見 `NOTICE`、`THIRD-PARTY-NOTICES`、`SBOM` | `[A]`（依檔案清單） |
| 授權一致性 | 程式碼、`skills/*.md`、`fixtures/*` 均在同一 repo，未見個別授權標頭 | `[A]` |

**散布義務（MIT）**：散布原始碼或二元形式時，必須保留著作權聲明與授權條文。目前 `LICENSE` 已存在，符合最低要求；建議另加第三方聲明檔（見第 6 節）。

**待確認**：`LICENSE` 的年份標示為 2026，若實際首次發表年份不同，建議校正為首次發表年份或「2026」以外的正確年份。此屬文件正確性問題，不影響授權效力。`[C]`

## 2. 執行期必要相依

| 相依 | 取得方式 | 授權（依現有證據） | 是否隨 repo 散布 | 相容性 | 證據 |
|---|---|---|---|---|---|
| Python 3.9+ 標準函式庫 | 使用者系統或官方發行版 | PSF License Agreement（寬鬆、與 GPL 相容） | 否 | 與 MIT 相容 | `[B]` |
| SQLite（含 FTS5） | Python 內建 `sqlite3` 模組 | Public Domain | 否 | 相容 | `[B]` |
| IANA 時區資料庫（`zoneinfo`／系統 tzdata） | 系統套件 | Public Domain | 否 | 相容 | `[B]` |
| 現代瀏覽器 | 使用者自備 | 各瀏覽器自有授權 | 否 | 不涉及 | `[A]` |
| Bash／POSIX shell | 使用者系統 | 各發行版授權 | 否 | 不涉及 | `[A]` |

README 與 ARCHITECTURE 明確聲明「Python 3.9 以上、零 pip 套件」，`install.sh` 只檢查 Python 版本並建立目錄，未執行任何套件安裝。`[A]`（`install.sh`）

## 3. 選用外部相依（未 vendored，僅執行期呼叫）

這一類**不隨 repo 散布**，因此不直接觸發 MIT 的散布義務；但仍是授權與服務條款風險，必須由 BOB 確認。

| 相依 | 啟用方式 | 授權／條款狀態 | 風險 | 證據／待辦 |
|---|---|---|---|---|
| `gog` CLI（Gmail 傳輸，[gogcli.sh](https://gogcli.sh)） | `accounts.json` 設 `driver: "gog"` | **未確認** `[C]` | 若授權禁止自動化或商業使用，會影響 live 模式；亦可能要求保留其授權聲明 | BOB 確認授權條款與可散布性 |
| `gsk`／Genspark CLI（Outlook 等傳輸） | `driver: "gsk"` | 專有 SaaS CLI，**未確認** `[C]` | 服務條款可能限制自動化擷取、資料用途或再散布；帳號認證狀態由使用者自行管理 | BOB 確認 ToS 是否允許此用法 |
| IMAP 伺服器（iCloud／Fastmail／Yahoo／Zoho／自訂） | `driver: "imap"` | 各供應商條款，**未確認** `[C]` | 部分供應商對應用程式密碼與自動同步有額外限制 | 使用說明已要求 App 專用密碼，屬良好實務 `[A]` |
| BYO agent：OpenAI 相容端點（OpenAI、Ollama、vLLM、LiteLLM 等） | `agent.json` 設 `driver: "openai_compatible"` | 各服務條款與**模型授權**（例如 Llama 系列有社群授權限制） | 模型授權可能限制商業用途或要求標示；資料外送涉及跨境傳輸（見 `DATA-INVENTORY.md`） | BOB 確認目標模型授權 |
| BYO agent：CLI（文件示例 `claude -p`） | `driver: "cli"` | 各 CLI 條款 | CLI 子程序可能自行連網，資料外送範圍不受本專案控制 | `[B]` |
| BYO agent：HTTP worker | `driver: "http"` | 由操作者自建 | 端點安全性與資料處理責任落在操作者 | `[B]` |
| ICS 行事曆來源（URL 或檔案） | 行事曆匯入 | 由來源決定 | URL 形式會對外發出請求，洩漏來源 IP 與存取行為；若 URL 內含權杖，將落到本機設定 | `[B]`，需確認 URL 儲存方式 `[C]` |
| MCP 客戶端（Claude Desktop、Cursor 等） | `server/mcp_server.py` stdio | 各客戶端條款 | 客戶端背後的雲端模型會取得工具輸出（郵件片段），屬實質外送 | `[B]` |

## 4. 開發與測試期相依

| 相依 | 用途 | 授權 | 是否隨發行物散布 | 相容性 | 證據 |
|---|---|---|---|---|---|
| `unittest`（Python 標準函式庫） | 測試 | PSF | 否 | 相容 | `[A]`（README 測試段） |
| Node.js（`node --check` 語法檢查） | 開發期 UI 檢查 | MIT | 否 | 相容 | `[B]`（ARCHITECTURE 第 7.2 節） |
| Headless Chrome／CDP（`tests/_tpi_mobile_cdp.js`） | 開發期 UI 驗證 | BSD-3-Clause 類 | 否 | 相容 | `[B]` |
| GitHub Actions（`.github/workflows/smoke.yml`） | CI | GitHub 服務條款 | 否 | 不涉及；**本輪不得修改此檔** | `[C]`（檔案內容未讀取） |

## 5. 授權相容性判定原則（供後續新增相依時使用）

以本專案為 MIT 的前提：

| 授權 | 判定 | 說明 |
|---|---|---|
| MIT、BSD-2/3-Clause、ISC、PSF、Public Domain／CC0 | **可接受** | 只需保留聲明 |
| Apache-2.0 | **可接受，需注意** | 需保留 `NOTICE`（若有）與變更說明；與 MIT 單向相容，但專利條款與終止條款需在意 |
| MPL-2.0 | **可接受，需注意** | 檔案層級 copyleft：修改過的 MPL 檔案需以 MPL 釋出 |
| LGPL-2.1/3.0 | **有條件接受** | 僅限動態連結、且需允許使用者替換函式庫；不利於「單一 process、零 pip」定位 |
| GPL-2.0/3.0、AGPL-3.0 | **不建議** | 散布或網路提供服務時可能要求整體以同授權釋出，與本專案 MIT 定位衝突 |
| 商業／專有條款（含部分 CLI 與模型授權） | **逐案確認** | 需確認是否允許自動化、商業使用、再散布 |
| CC-BY-SA、CC-BY-NC 文件授權 | **不建議引入程式碼或文件** | 授權擴散或限制商業使用，與 MIT 專案不相容 |

**Allowlist 建議**：把上表前三列寫成 CI 檢查規則（見 `ACTION-PLAN.md` P2-1），新增相依時必須在 `DEPENDENCIES.md` 補一列並附授權來源連結。

## 6. 缺口與建議

| # | 缺口 | 影響 | 建議 | 優先級 |
|---|---|---|---|---|
| L1 | 無第三方聲明檔（`THIRD-PARTY-NOTICES`） | 若未來新增 vendored 程式碼或 pip 套件，散布時可能違反授權義務 | 先立草案（目前內容僅標準函式庫與 public domain，可寫成「本專案未內含第三方程式碼」的聲明），未來再擴充 | P1 |
| L2 | 無 SBOM／相依清單自動化 | 無法快速回答「用了哪些授權」 | 產生 SPDX 或 CycloneDX 格式的最小 SBOM（僅列標準函式庫與選用外部相依），存於 `docs/fmb-compliance/` 或 CI artifact | P2 |
| L3 | 未確認 `gog`／`gsk`／模型授權 | 可能在商業使用時違反條款 | BOB 逐一確認，結論寫回本文件第 3 節 | P0（商業使用前） |
| L4 | 專案名稱不一致（openinbox／TooPowerInbox／yhbmail／GenMail 對照） | 商標與授權文件易混淆；README 已聲明與 GenSpark 無關，屬良好實務 | 對外文件統一主名稱，並保留「與任何廠商產品無關」的免責句 | P2 |
| L5 | `LICENSE` 年份 | 文件正確性 | 校正為首次發表年份 | P2 |
| L6 | 未見 contrib 授權條款（DCO／CLA） | 外部貢獻的授權來源不清楚 | 在 `CONTRIBUTING.md` 加一句「提交即同意以 MIT 授權釋出」（需 BOB 決定是否改既有檔案） | P2 |
| L7 | `fixtures/` 與 `skills/` 未標示授權 | 散布時易被誤認為第三方內容 | 在 `THIRD-PARTY-NOTICES` 或 README 註明「由本專案以 MIT 釋出，內容為虛構」 | P2 |

## 7. 決策點（授權面）

| 決策 | 保守預設 | 替代方向 |
|---|---|---|
| 是否允許 GPL／AGPL 相依 | 不允許 | 若必要，改為獨立程序呼叫並確認法律意見 |
| `gog`／`gsk` 是否列入「支援組合」 | 文件標為「使用者自備、未經授權確認」 | BOB 取得授權確認後升級為正式支援 |
| 是否建立 SBOM | 先做最小清單 | 導入自動化 SBOM 產生與 CI 檢查 |
| 是否採用 DCO | 先以文件說明 | 加入 CLA 流程 |
