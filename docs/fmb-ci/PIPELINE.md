# 流程設計

本文件描述 CI 的觸發條件、權限邊界、job 拓撲、快取、產出物與失敗處理。所有 job 名稱與 `TEMPLATE-ci-workflow.md` 一致；若要改 matrix，必須同步更新 branch protection 的 required checks。

## 1. 觸發條件

| 事件 | 工作流程 | 說明 |
|---|---|---|
| `pull_request` → `main` | `ci.yml` | 主要阻擋路徑。fork PR 同權限（唯讀），不需要 secret |
| `push` → `main` | `ci.yml` | 合併後確認 main 仍為綠燈 |
| `push` tag `v*` | `tag-artifact.yml` | 只在標籤上產生 GitHub Release 附件 |
| `schedule`（每日） | `nightly.yml` | 慢檢查、舊版 Python、macOS、完整 git 歷史秘密掃描 |
| `workflow_dispatch` | 全部 | 手動重跑，不改變判定 |

刻意**不**使用 `pull_request_target`（會把寫入權限暴露給 PR 內容），也不在 PR 觸發的 workflow 裡 checkout 後保留憑證（`persist-credentials: false`）。

## 2. 權限與安全基線

```text
workflow 層級：permissions: { contents: read }
job 層級：只有 tag-artifact 的 produce job 取得 contents: write
repository secrets：不使用
環境（environment）：不使用
```

- 所有 `uses:` 一律 pin 到完整 commit SHA，版本標籤只留作註解；由 Dependabot 定期提 PR 更新。
- `actions/checkout` 加上 `persist-credentials: false`，避免 GITHUB_TOKEN 留在 `.git/config`。
- 不在 workflow 中 `echo` 任何環境變數內容；`env` 只放固定字串（時區、Python 行為）。
- 秘密掃描與政策守門的輸出必須 redact：只印檔名、行號、規則名稱，不印命中字串。
- Actions 允許清單建議只開放 `actions/*`、`github/*`；第三方 action 一律改用 CLI＋固定版本＋校驗碼的方式執行（gitleaks 就是這樣處理）。

## 3. 執行環境

| 項目 | 值 | 理由 |
|---|---|---|
| Runner | `ubuntu-24.04` | 固定版本，不用 `ubuntu-latest`，避免映像更新造成漂移 |
| Python（G1） | 3.9、3.12、3.13 | 3.9 是支援下限，3.13 是現行開發版本，3.12 是中間保險 |
| Python（測試） | 3.9（G2）＋3.13（G4） | 每個版本只跑一次完整測試 |
| `TZ` | `UTC` | 行事曆與時間相關測試需要固定時區，避免本地時區造成差異 |
| `OPENINBOX_NO_BROWSER` | `1` | 不在 CI 開瀏覽器 |
| `PYTHONDONTWRITEBYTECODE`／`PYTHONHASHSEED` | `1`／`0` | 減少非必要寫檔與雜湊順序差異 |
| Node | runner 內建，只用 `node --check` | 本 repo 沒有 npm 建置步驟 |

## 4. Job 拓撲

```text
syntax (G1, matrix 3.9/3.12/3.13)
  ├── tests     (G2, matrix 3.9)
  ├── smoke     (G3)
  ├── coverage  (G4, 3.13 + 覆蓋率報告)
  ├── lint      (G5)
  ├── types     (G6, 觀察)
  ├── deps      (G7)
  ├── secrets   (G8)
  └── policy    (G9)

package (G10) 需要 tests + smoke 通過
```

設計理由：

- G1 是最便宜的失敗點，放最前面可以讓打錯字或 typedef 錯誤在 1 分鐘內回報。
- G2～G9 彼此獨立，`fail-fast: false`，一次回報所有問題，避免來回修。
- G10 只依賴 G2／G3，因為它要驗證的是「這份原始碼能不能被安裝與啟動」，不是全部靜態檢查。

## 5. 各 job 說明

### G1 語法

- `python -m compileall -q server fmb_feature2 scripts tests`：把每個 `.py` 編成 bytecode，抓語法錯誤與 `from __future__` 位置錯誤。比 import 整套模組快，且不會觸發資料庫或檔案副作用。
- `node --check` 逐一檢查 `ui/modules/*.js`、`ui/pwa/sw.js`、`tests/_tpi_mobile_cdp.js`：只驗語法，不執行、不連網。
- 只在 3.13 那一格跑 JS 檢查，避免重複三次。

### G2 單元測試

- 只跑 Python 3.9：確認下限版本仍可用（PEP 604 型別註解、`match`、新標準函式庫 API 都會在這裡現形）。
- 輸出以 `tee` 落地，失敗時上傳 artifact，避免只在日誌裡找錯誤。
- 3.13 的完整測試由 G4 覆蓋。

### G3 smoke

- 直接跑 `scripts/smoke.sh`：它會解析 `smoke.yml` 的 run 步驟，在拋棄式副本執行，並在 8770 被占用時自動換埠。
- 已知重疊：`smoke.yml` 內含 unittest 步驟，因此 G3 會再跑一次測試。若時間預算吃緊，優先把它降級為「只在 push main 跑」，而不是改 `smoke.sh`（那需要動既有檔案）。
- 預期 `smoke.yml` 之後仍會演進，G3 自動跟隨，這是刻意的設計。

### G4 覆蓋率

- 只有這個 job 安裝 `requirements-dev.txt`（coverage、ruff、mypy、pip-audit），執行期仍零相依。
- `coverage run --branch -m unittest discover -s tests` → `coverage report` → `coverage xml`。
- 門檻用獨立 step（`coverage report --fail-under=N`）：階段 0 為 0（永遠通過，只記錄），階段 2 起改為實際門檻並移除 `continue-on-error`。
- `coverage.xml` 上傳為 artifact，保留 14 天，方便追蹤趨勢。

### G5 lint

- `ruff check --output-format=github .`：輸出直接變成 PR 註解。
- 規則集刻意很小（`E4`、`E7`、`E9`、`F`）：這些是「一定會壞」的錯（未定義名稱、重複定義、語法級問題、f-string 錯誤），誤報率低，適合作為第一天就阻擋的關卡。
- `ruff format --check` 只記錄不阻擋，因為大規模重排會製造無意義 diff，且本 repo 沒有統一格式化的歷史。

### G6 型別

- `mypy` 依 `pyproject.toml` 設定對 `server`、`scripts` 執行。
- 本 repo 目前沒有完整型別註解，因此以**不新增錯誤數**為判準；錯誤數寫在 PR 說明，不自動比對（比對需要保存基線，屬後續優化）。
- 全程 `continue-on-error: true`。

### G7 相依掃描

- `pip-audit -r requirements-dev.txt --strict`：只涵蓋 CI 工具鏈。
- 另外 `python -m pip check` 確認安裝後的相依一致。
- 執行期零 pip 是個強保證：`server/` 若出現第三方 import，會由 G9 直接擋下。

### G8 秘密掃描

- 不用第三方 action，改為下載固定版 gitleaks、驗證 release 的 checksum 檔、再執行；避免把 `GITHUB_TOKEN` 交給第三方 action。
- PR 階段用 `--no-git --redact`（掃工作目錄，快）；完整 git 歷史掃描放 nightly。
- 界限說明：downloaded checksum 與 binary 同源，強度不如寫死 digest。**採用時應把 SHA256 直接寫進 workflow**，這是列在 `ROLLOUT.md` 的待辦。

### G9 repo 政策守門

`scripts/ci/policy_guard.py` 檢查三件事：

1. `server/`、`scripts/` 只 import 標準函式庫或本 repo 模組（守住「零 pip」）。
2. repo 檔案不出現真實憑證格式的前綴（`fixtures/`、`docs/` 除外；命中時只印檔名與行號）。
3. `.github/workflows/` 不含部署、發佈套件、推送映像的指令（守住「不部署」）。

### G10 建置與啟動

- `git archive` 產生以 commit SHA 命名的來源壓縮檔與 `SHA256SUMS`，這是本專案唯一有意義的「建置產物」（無編譯步驟、無打包步驟）。
- 解到 `mktemp -d` 的乾淨目錄，跑 `./install.sh`（會複製 `accounts.example.json` → `accounts.json`，全程示範模式），以隨機埠啟動 `server/app.py`，輪詢 `/api/health` 與 `/api/features`，最後關閉。
- 這一步等於驗證「新人 clone 下來能不能跑」，補上 smoke 沒涵蓋的安裝流程。

## 6. 快取策略

- 只有需要 `requirements-dev.txt` 的 job 使用 `actions/setup-python` 的 `cache: pip`，並以 `requirements-dev.txt` 為 cache key。
- 不快取 `data/`、`vault/`、`*.db`：這些是本機資料，CI 不該帶狀態。
- 不啟用 `actions/cache` 自訂快取，避免跨 job 傳遞不必要的檔案。

## 7. 併發與取消

```text
ci.yml        concurrency: ci-<workflow>-<ref>, cancel-in-progress 只在 PR
tag-artifact  concurrency: tag-<ref>, 永不取消
nightly       concurrency: nightly, 永不取消
```

- PR 上連續 push 會取消前一次執行，省 runner 分鐘數。
- `main` 與標籤上的執行不取消，保留完整紀錄作為稽核依據。

## 8. 產出物

| Artifact | 產生 job | 保留 | 內容 |
|---|---|---|---|
| `unittest-log-py<ver>` | G2 | 7 天 | 只有失敗時上傳的測試日誌 |
| `coverage` | G4 | 14 天 | `coverage.xml` |
| `mypy-report` | G6 | 7 天 | 型別檢查輸出（每次上傳，供趨勢參考） |
| `openinbox-<sha>.tar.gz`、`SHA256SUMS` | G10／G11 | 14 天（tag 則永久隨 Release） | 可重現來源壓縮檔與校驗碼 |

產出物不含 `accounts.json`、`agent.json`、`data/`、`vault/`，也不含測試日誌中的信箱內容（測試只用虛構 fixture）。

## 9. 失敗處理與 flaky 政策

1. **不自動重試**。重試會掩蓋真正的競態；若某測試間歇失敗，開 issue 修它，而不是加 retry。
2. **失敗訊息要能自己站得住**：每個 step 印出可重現的單行指令（例如 `python3 -m unittest discover -s tests`），讓人在本機一次重跑。
3. **flaky 標記**：確認是環境問題（例如埠占用、時區）才降級為 `continue-on-error`，並在 PR 說明寫上原因與期限。
4. **連續紅燈**：`main` 紅燈超過一輪 orchestrator 週期時，暫停派工，先修 CI（避免把紅燈當常態）。

## 10. 刻意不在 CI 做的事

- 不連線到正式 IMAP、Gmail、Outlook、任何 Agent 端點。
- 不使用 repository secret 或 environment secret。
- 不跑 `install.sh` 以外的安裝行為，不下載 `gog`／`gsk` CLI。
- 不執行 `node`（除了 `--check`）、不跑瀏覽器、不跑 CDP（nightly 另議）。
- 不做部署、不做映像建置、不發佈套件。
- 不把郵件內容、客戶資料或真實信箱寫進日誌或 artifact。
