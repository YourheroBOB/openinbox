# Openinbox CI／品質關卡提案

本目錄是 **提案文件**，不是可執行設定。這裡只放 Markdown：設計說明、關卡定義、可直接抄用的設定範本。實際的 `.github/workflows/*` 與其他工具設定檔，請由 maintainer 另開 PR 建立（本目錄的 PR 依規定不觸碰 `.github/`）。

## 1. 目的與範圍

目標是替 `YourheroBOB/openinbox` 補上一條**可預期、可回退、對本機優先定位友善**的 CI 流程，涵蓋：

1. 語法與位元組碼編譯（Python＋前端 JavaScript）。
2. 單元測試（`python3 -m unittest discover -s tests`）。
3. smoke 回歸（`scripts/smoke.sh`）。
4. 覆蓋率（記錄、棘輪、最後才阻擋）。
5. 相依掃描（只涵蓋 CI 工具鏈，因為執行期刻意零 pip）。
6. 秘密掃描（gitleaks，redact）。
7. repo 政策守門（零 pip 相依、無真實憑證、workflow 不含部署／發佈）。
8. 建置（可重現來源壓縮檔＋乾淨目錄啟動健康檢查）。
9. 標籤產出（GitHub Release 附件；不發佈套件、不部署）。

明確**不在**本提案：

- 不建立 workflow 檔、不改 `.github/workflows/smoke.yml`。
- 不引入任何 repository secret、不加部署金鑰、不改 Git remote。
- 不發佈到 PyPI、不推 Docker 映像、不部署到任何主機。
- 不對正式 IMAP／Agent／郵件服務做自動測試。
- 不引入執行期 pip 相依（`server/` 仍只使用標準函式庫）。

## 2. 現況基線（依 repo 現有內容）

| 項目 | 現況 | 對 CI 的意義 |
|---|---|---|
| 測試 | `python3 -m unittest discover -s tests`，標準函式庫 unittest，使用拋棄式資料夾 | 零額外相依即可在 CI 執行 |
| smoke | `scripts/smoke.sh` 會解析 `.github/workflows/smoke.yml` 的 run 步驟，在拋棄式副本執行 | G3 直接沿用，smoke.yml 改了它也跟著改 |
| 執行期相依 | 零 pip；Python 3.9 以上；Node 只在開發時做 `node --check` | 相依掃描範圍只有 CI 工具鏈 |
| 前端 | `ui/index.html`、`ui/modules/*.js`、`ui/pwa/sw.js`，無 npm／打包步驟 | 「建置」＝語法檢查＋來源壓縮檔 |
| 網路 | 伺服器只聽 `127.0.0.1`；測試用本機假 IMAP 與本機假 agent | CI 不需要任何外部服務憑證 |
| 合併流程 | orchestrator 每 15 分鐘派工與合併（見 `STATE.md`） | **阻擋關卡必須快**，慢的全部丟 nightly |
| 規模 | STATE.md 記錄 711 個 unittest 全綠 | 測試本身很快，時間主要花在環境安裝 |

## 3. 設計原則

1. **快，才擋得住**：阻擋路徑（PR 必須通過的 job）目標 8 分鐘內結束；超過 15 分鐘的檢查放 nightly。理由是本 repo 由 15 分鐘一輪的 orchestrator 驅動，慢關卡會拖垮整個派工節奏。
2. **每個 Python 版本只跑一次測試**：下限 3.9 跑純測試（G2），現行 3.13 在覆蓋率 job（G4）順便跑，避免重複。
3. **零執行期相依的複查，用機器驗**：`server/` 不得 import 第三方套件，由 `scripts/ci/policy_guard.py` 驗，而不是靠人工審查。
4. **先觀察、後阻擋**：新關卡一律以 `continue-on-error` 上線一週，確認沒有誤報才轉為阻擋（見 `ROLLOUT.md`）。
5. **預設最小權限、不碰 secrets**：workflow 層級 `permissions: contents: read`；只有標籤產出 job 取得 `contents: write`。任何 job 都不需要 repository secret。
6. **掃描不得印出命中內容**：秘密掃描一律 `--redact`；政策守門只印檔名與行號。
7. **可回退**：每個關卡都是獨立 job，回退＝單一 PR 把它改成 `continue-on-error: true`，不影響其他關卡。

## 4. 關卡總覽

| 編號 | 關卡 | 阻擋？ | 一句話 |
|---|---|---|---|
| G1 | 語法（compileall＋`node --check`） | 是 | 最快失敗，最先跑 |
| G2 | 單元測試（Python 3.9 下限） | 是 | 0 failure／0 error |
| G3 | smoke 回歸（Linux） | 是 | `scripts/smoke.sh` exit 0 |
| G4 | 覆蓋率（Python 3.13 測試＋報告） | 測試是；門檻階段 2 起 | 先記錄，再棘輪 |
| G5 | lint（ruff） | 是（錯誤類規則） | 抓未定義名稱、錯字型 bug |
| G6 | 型別（mypy） | 否（觀察） | 只要求錯誤數不增加 |
| G7 | 相依掃描（pip-audit） | 是 | 無 high／critical |
| G8 | 秘密掃描（gitleaks） | 是 | 0 命中，日誌 redact |
| G9 | repo 政策守門 | 是 | 零 pip、無真憑證、workflow 無部署 |
| G10 | 建置＋啟動 | 是 | 來源壓縮檔＋乾淨目錄 `/api/health` |
| G11 | 標籤產出（GitHub Release 附件） | 僅標籤 | 不發佈套件、不部署 |

## 5. 文件索引

| 檔案 | 內容 |
|---|---|
| `PIPELINE.md` | 觸發條件、權限、job 順序、快取、產出物、失敗處理、時間預算 |
| `GATES.md` | 每個關卡的判準、門檻、棘輪、例外流程、審查清單 |
| `TEMPLATE-ci-workflow.md` | `.github/workflows/ci.yml` 可直接採用的範本 |
| `TEMPLATE-release-workflow.md` | `.github/workflows/tag-artifact.yml` 與 nightly 範本 |
| `TEMPLATE-tooling.md` | `requirements-dev.txt`、`pyproject.toml`（ruff／mypy／coverage） |
| `TEMPLATE-security.md` | `.github/dependabot.yml`、`.gitleaks.toml`、`scripts/ci/policy_guard.py`、repo 設定檢查清單 |
| `ROLLOUT.md` | 分階段上線、回退、時間預算、需要 BOB 決策的事項 |

## 6. 採用方式（給 maintainer）

1. 先讀 `ROLLOUT.md` 的階段 0，確認時間預算與 orchestrator 節奏不衝突。
2. 開一支 PR，只新增工具設定與 workflow 檔（內容直接取自 `TEMPLATE-*`），所有新 job 先掛 `continue-on-error`。
3. 一週後開第二支 PR，把 G1／G2／G3／G5／G7／G8／G9／G10 轉為阻擋，並在 branch protection 勾選對應檢查名稱。
4. 覆蓋率與型別檢查依 `GATES.md` 的棘輪節奏逐週收緊。

本目錄的所有設定範本都沒有寫入任何憑證值、真實信箱或客戶資料；需要假值的地方一律使用 `FAKE_VALUE_FOR_TEST` 這類明顯假字串與 `example.com`／`.example` 虛構網域。
