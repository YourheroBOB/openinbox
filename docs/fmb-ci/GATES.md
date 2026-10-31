# 關卡定義、門檻與棘輪

本文件是「什麼情況算通過」的唯一依據。任何關卡的阻擋狀態變更，都要在 PR 說明引用本文件的段落編號。

## 1. 關卡總表

| 編號 | Job 名稱（branch protection 用） | 工具 | 階段 0 | 目標狀態 | 判準 |
|---|---|---|---|---|---|
| G1 | `G1 syntax (py3.9)`、`(py3.12)`、`(py3.13)` | `compileall`＋`node --check` | 阻擋 | 阻擋 | 全綠，0 錯誤 |
| G2 | `G2 unittest (py3.9)` | unittest | 阻擋 | 阻擋 | 0 failure／0 error |
| G3 | `G3 smoke (Linux)` | `scripts/smoke.sh` | 阻擋 | 阻擋 | exit 0 |
| G4 | `G4 coverage` | coverage.py | 測試阻擋、門檻觀察 | 門檻阻擋 | 見 §3 |
| G5 | `G5 lint (ruff)` | ruff | 阻擋（小規則集） | 阻擋 | 0 錯誤；`E501`／格式檢查不計 |
| G6 | `G6 types (mypy, advisory)` | mypy | 觀察 | 觀察→局部阻擋 | 見 §5 |
| G7 | `G7 dependency audit` | pip-audit | 阻擋 | 阻擋 | 無 high／critical |
| G8 | `G8 secret scan` | gitleaks | 阻擋（先觀察一週） | 阻擋 | 0 命中 |
| G9 | `G9 repo policy guard` | `policy_guard.py` | 阻擋 | 阻擋 | 0 違規 |
| G10 | `G10 package + startup` | git archive＋curl | 阻擋 | 阻擋 | 產物存在、`/api/health` 200 |
| G11 | （標籤才觸發） | gh CLI | 手動 | 手動 | 見 `TEMPLATE-release-workflow.md` |

> 階段 0 的「阻擋」是相對的：新 workflow 上線第一週，建議連 G8／G9 都先 `continue-on-error`，確認沒有誤報再開鍘。詳見 `ROLLOUT.md`。

## 2. G1／G2／G3：不可協商的三關

- **G1**：`compileall` 必須涵蓋 `server`、`fmb_feature2`、`scripts`、`tests`。新增目錄時要一起加進去，否則新目錄的語法錯誤會漏掉。
- **G2**：只跑 Python 3.9。任何降到 3.10 以上才有的語法（`X | Y` 型別註解在執行期求值、`match`）都會在這裡失敗；這是本專案宣稱「Python 3.9 以上」的唯一機器保證。
- **G3**：必須是 Linux。smoke 會起真伺服器並 curl，需要 `mktemp`、`bash`、`curl`；Windows runner 不支援，不要嘗試。

例外流程：G1～G3 不接受例外。若因環境問題紅燈，修環境或降級該 step，不可放行合併。

## 3. G4：覆蓋率棘輪

覆蓋率是本提案中唯一採「逐步收緊」的關卡。

| 階段 | `--fail-under` | `continue-on-error` | 動作 |
|---|---|---|---|
| 0 | `0` | 門檻 step 為 `true` | 只記錄 `coverage.xml`，建立基線 |
| 1 | 0 | 門檻 step 維持 `true` | 由基線算出建議值，寫進 PR 說明 |
| 2 | 基線向下取整到 5 的倍數 | 移除，開始阻擋 | 低於門檻即紅燈 |
| 3 | 每完成一個里程碑 +5 | 阻擋 | 上限 85%，超過就不再往上加 |

規則：

- 只看**行覆蓋率**（line rate）作門檻，分支覆蓋率只記錄。
- 門檻以 `server/`、`scripts/` 為分母；`fmb_feature2/` 屬於原型程式碼，不計入。
- 純文件 PR 不需為覆蓋率下降負責：若 diff 只含 `docs/`、`*.md`、`fixtures/`，允許覆蓋率不變。
- 降低門檻必須是獨立 PR，並在說明寫明「為什麼降、何時補回」。

## 4. G5：lint 的邊界

啟用的規則集：`E4`（import 相關）、`E7`（敘述層級錯誤）、`E9`（執行期錯誤）、`F`（pyflakes：未定義名稱、重複定義、未使用 import 等）。

- `E501`（行長）不啟用：本 repo 沒有統一換行寬度，開了只會製造噪音。
- `ruff format --check` 只記錄，不阻擋；若日後要啟用，必須是一次獨立的「純格式化」PR，且不與功能變更混在一起。
- 例外方式：在該行加 `# noqa: <code>` 並在 PR 說明寫理由，不使用全檔案 `# ruff: noqa`。

## 5. G6：型別檢查的棘輪

1. 第一週：`continue-on-error: true`，只把錯誤數與前五大模組寫進 PR 說明。
2. 第二階段：選定 2～3 個「邊界乾淨」的模組（建議 `server/features/_ics.py`、`server/features/_origin.py` 這類純函式為主的檔案），要求**零錯誤**。
3. 第三階段：擴大到 `server/` 全部，仍以「錯誤數不增加」為判準。

不要一次對全 `server/` 開嚴格模式：`yhbmail.py`、`app.py` 耦合本機狀態與 HTTP 處理，強制標註會產生大量與價值無關的 diff。

## 6. G7：相依掃描的實際範圍

- 執行期**零**相依 → 不存在執行期 CVE 風險面。
- G7 只掃 `requirements-dev.txt`：coverage、mypy、pip-audit、ruff。
- 嚴重度政策：`high`／`critical` 直接阻擋；`medium` 開 issue，不阻擋；`low` 只記錄。
- 若 pip-audit 對某個 CI 工具有無法修補的通報，處理方式是**升級或替換該工具**，不是加忽略清單。

## 7. G8：秘密掃描的 allowlist 治理

- allowlist 只允許兩類：`fixtures/`、`docs/fmb-ci/`（本目錄充滿範例），以及明確字串 `FAKE_VALUE_FOR_TEST`。
- 絕不 allowlist `tests/` 整個目錄：測試檔是最容易貼上真憑證的地方，必須持續掃。
- 命中時的處理順序：① 立刻撤銷該憑證 ② 從歷史清除 ③ 才討論 allowlist。**不要**為了讓 CI 變綠而加 allowlist。
- 日誌一律 `--redact`；reviewer 不要求貼出命中內容。
- 建議同時開啟 GitHub 原生 secret scanning 與 push protection（repo 設定，非 YAML；見 `TEMPLATE-security.md` §4）。

## 8. G9：政策守門判準

| 檢查 | 通過條件 | 為什麼需要 |
|---|---|---|
| 零 pip 相依 | `server/`、`scripts/` 的 import 只落在標準函式庫或本 repo 模組 | 這是本專案的產品承諾，必須機器驗證 |
| 無真實憑證 | 檔案內沒有「前綴＋足夠長字元」的字串 | 補 gitleaks 的漏洞（自製格式、低熵金鑰） |
| workflow 無部署 | `.github/workflows/*` 不含部署／發佈套件／推送映像指令 | 守住「不部署、不寄信、不改遠端」 |

誤判處理：優先改寫被掃到的內容（例如把字面量拆開），而不是加豁免；真的必須豁免時，在 `policy_guard.py` 加明確的檔案路徑豁免並註明理由。

## 9. G10：建置判準

必須同時滿足：

1. `git archive` 產出的壓縮檔存在，且 `SHA256SUMS` 可驗證。
2. 解壓到 `mktemp -d` 後，`./install.sh` 成功。
3. `server/app.py` 在 20 秒內讓 `/api/health` 回應 200。
4. `/api/features` 可回應（確認外掛載入器沒有壞）。
5. 程序在 job 結束時被關閉（`trap ... EXIT`），不留下背景埠。

不驗證：UI 畫面、瀏覽器行為、真實信箱同步（那些需要外部服務或瀏覽器）。

## 10. 無法自動化的關卡（人工審查清單）

CI 綠燈不等於可以合併。reviewer 仍需確認：

- [ ] 沒有新增預設寄信路徑，也沒有繞過人工確認的 Agent 工具。
- [ ] 沒有新增遙測、託管模型或執行期 pip 相依。
- [ ] 新增的測試使用 `tempfile`／`tmp_path` 與虛構資料，未連正式服務。
- [ ] 沒有真實信箱、客戶名稱、案件當事人資料或訊息內文進入 repo。
- [ ] 新的 UI 字串同時有繁中與英文，且不是簡體。
- [ ] 沒有修改 `secrets`、憑證設定、Git remote 或部署流程。
- [ ] 若動到 `scripts/smoke.sh` 或 `.github/workflows/smoke.yml`，G3 仍能在本機重現。

## 11. 時間預算

| 路徑 | 目標 | 對策 |
|---|---|---|
| 阻擋路徑（G1＋G2＋G3＋G5＋G7＋G8＋G9＋G10） | < 8 分鐘 | G1 先跑、matrix 最小化、每個版本只測一次 |
| 觀察路徑（G4＋G6） | < 15 分鐘 | 可與阻擋路徑平行 |
| nightly | < 40 分鐘 | 慢檢查全部集中在這裡 |

若阻擋路徑超過 10 分鐘，依序降級：① G3 改為只在 push main 跑 ② G7 改為每日跑 ③ G1 的 3.12 拿掉。不要動 G1 的 3.9／3.13 與 G2。
