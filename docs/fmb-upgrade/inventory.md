# 語言版本、相依套件與執行環境盤點

本檔依據 repo 快照與已提供檔案內容盤點。標記「待確認」者表示快照未提供實際安裝版本或檔案內容，需在目標環境量測，不可推定為正式結論。

## 1. 總覽判斷

| 判斷 | 說明 |
|---|---|
| 內建 Python 相依極少 | repo 沒有 `requirements.txt`、`pyproject.toml`、`package.json`、lock 檔；核心宣告為 Python 3.9+ 標準函式庫 |
| 主要過時風險在語言版本政策 | README、CONTRIBUTING、ARCHITECTURE 都寫 Python 3.9+；Python 3.9 已過安全維護期 |
| 次要風險在執行環境差異 | SQLite／FTS5 是否可用取決於 Python 建置選項；Node、瀏覽器、Bash 版本會影響測試與 UI 行為 |
| 外部選擇性相依不受 repo 鎖定 | IMAP、`gog`／`gsk`、OpenAI 相容端點、CLI／HTTP Agent、ICS feed 都屬於外部執行期，需契約測試而非自動升級 |

## 2. 語言與執行期盤點

| 項目 | repo 宣告／快照證據 | 待確認 | 過時或已知風險 | 建議方向 |
|---|---|---|---|---|
| Python | `README.md`、`README.zh-Hant.md`、`CONTRIBUTING*`、`docs/fmb/ARCHITECTURE.md` 皆為 Python 3.9+；`run.sh` 以 `python3 server/app.py` 啟動 | 目標機實際 `python3 --version` | Python 3.9 已過安全維護期；3.10 也接近退役；繼續以 3.9 為下限會擴大安全面 | 最低升至 3.11，測試矩陣 3.11–3.13 |
| Python 相依套件 | 零 pip；`CONTRIBUTING.md` 明列 stdlib only | 是否有開發者本機自行安裝全域套件影響測試 | 無 lock 檔，但因為沒有外部 Python 相依，風險主要來自環境漂移 | 維持零 pip；在文件與 CI 矩陣宣告版本 |
| Bash | `run.sh` 使用 `#!/usr/bin/env bash`、`set -euo pipefail`；`install.sh`、`scripts/smoke.sh` 存在但內容未提供 | 目標機 `bash --version`；`install.sh` 是否使用 Bash 4+ 功能 | macOS 預設 Bash 3.2，若腳本用到關聯陣列等會有相容問題 | 先用 `bash -n` 與乾淨暫存根目錄驗證；未確認前不要求 Bash 5 |
| Node.js | 無 `package.json`；repo 有 `tests/_tpi_mobile_cdp.js` 與 `ui/modules/*.js`；文件提及 Node 主要用於開發期 JS 檢查 | 目標機 `node --version`；哪些測試會跳過 | Node 缺少時 UI 檢查可能被跳過，造成假綠燈 | Node 僅列為開發檢查相依，CI 不應因缺少 Node 而跳過核心 Python 測試 |
| 瀏覽器／PWA | README 支援 Mac／Windows／iOS／Android PWA；`ui/modules/agents.js` 使用 optional chaining、nullish coalescing、箭頭函式、模板字串 | 最低支援瀏覽器版本矩陣 | 舊瀏覽器不支援現代 JS；沒有 build／transpile 流程 | 明訂支援現代瀏覽器；不輕易引入 npm build pipeline |
| 作業系統 | README 以 Unix shell 安裝與執行；Windows 主要以 PWA 方式使用 | Windows 是否有受支援的 server 啟動路徑 | `run.sh`／`install.sh` 非 Windows 原生 | 在文件區分「本機伺服器支援 Unix/Linux/macOS」與「PWA 客戶端支援平台」 |

## 3. 內建技術與協定盤點

| 項目 | repo 宣告／快取證據 | 待確認 | 風險 | 建議方向 |
|---|---|---|---|---|
| SQLite | `docs/fmb/ARCHITECTURE.md` 顯示主要資料庫為 `data/openinbox.db`，透過 Python `sqlite3` | 實際 `sqlite3.sqlite_version` | 不同 Python 封裝的 SQLite 版本不同；行為與錯誤碼可能不同 | 在 CI 與本機記錄版本；涉及 schema 變更時先備份 |
| FTS5 | 架構文件明列 FTS5 為選用，缺少時回落 `LIKE` | 目標環境是否可建立 FTS5 虛擬表 | 升級 Python 後 FTS5 可能可用性改變；索引重建需可重入 | 以假資料測試 FTS5 與 LIKE 結果一致性 |
| HTTP 面板 | `server/app.py` 只監聽 `127.0.0.1:8770`，`OPENINBOX_PORT` 可改埠 | 防火牆、SSH 通道、埠佔用 | 環境差異可能導致啟動或連線問題 | smoke 使用本機 loopback 與臨時埠 |
| MCP | README 使用 JSON-RPC 2.0、逐行 stdio、protocolVersion `2025-06-18`，工具含 `list_inbox`、`brain_board`、`search_brain`、`persona`、`save_draft` | 用戶端實際 MCP 版本 | 協定升級可能造成舊客戶端不相容；新工具可能讓上下文過大 | 維持舊工具相容，新增欄位可安全忽略 |
| PWA Service Worker | 架構文件與 README 明列只快取靜態檔，不碰 `/api/*` | service worker 快取版本命名與更新流程 | UI 升級後舊 service worker 可能提供過期 JS | 任何 UI 資產變更都要提升快取版本並測試更新 |
| 本機資料格式 | SQLite 具多張內部表；`data/`、`vault/`、`accounts.json`、`agent.json`、`rules.json` 皆在本機且多數 gitignore | schema 版本、遷移機制、備份工具 | repo 尚無內建完整備份／還原；直接複製 SQLite 可能不一致 | 升級前用 SQLite backup API 備份，遷移先 dry-run |

## 4. 可選外部相依盤點

| 外部相依 | 啟用方式 | 資料外送風險 | 升級策略 |
|---|---|---|---|
| IMAP 供應商 | `accounts.json` 的 `driver: "imap"`，支援 `icloud`、`fastmail`、`yahoo`、`zoho` 或自訂 host／port | 收件匣郵件內容、登入憑證經環境變數 | 不自動升級；以假 IMAP 驗證 EXAMINE／BODY.PEEK 唯讀行為 |
| `gog` CLI | Gmail 帳號 | 郵件同步範圍 | 不自動升級；契約測試與版本範圍需 BOB 決策 |
| `gsk` CLI | Outlook／額外 IMAP 傳輸 | 郵件同步範圍 | 不自動升級；只作為郵件傳輸，不啟用 Agent 行為 |
| OpenAI 相容端點 | `agent.json` 的 `openai_compatible` | context pack、查詢或草稿相關內容 | 不自動升級；錯誤正規化，失敗回落本機啟發式 |
| CLI Agent | `agent.json` 的 `cli` | context pack 經 stdin，子程序可能自行連網 | 不自動升級；逾時與錯誤處理需測試 |
| HTTP Agent worker | `agent.json` 的 `http` | context pack 經 HTTP POST | 不自動升級；建議 loopback 或受控網段 |
| ICS feed | 行事曆匯入 | 行事曆內容 | 不自動升級；重複匯入、取消、改期需有測試 |

## 5. 本機量測指令（不連正式服務）

以下指令可在目標環境執行，用來補足「待確認」欄位：

```bash
python3 --version
python3 -c 'import sqlite3,sys; print(sys.version); print(sqlite3.sqlite_version)'
python3 - <<'PY'
import sqlite3
con = sqlite3.connect(":memory:")
try:
    con.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
    print("fts5=yes")
except sqlite3.OperationalError as e:
    print("fts5=no", type(e).__name__)
PY
bash --version | head -n 1
node --version || true
git --version
```

瀏覽器與 PWA 建議另外記錄：

| 平台 | 需記錄內容 |
|---|---|
| Chrome／Edge | 版本、安裝 PWA、service worker 更新行為 |
| Firefox | 版本、面板核心流程 |
| Safari／iOS | 版本、加入主畫面、離線頁 |
| Android Chrome | 版本、底部分頁與 PWA |

## 6. 盤點結論

1. **最需要優先處理**：Python 3.9 下限已過時，應分階段升至 3.11。
2. **不可忽略**：SQLite／FTS5 與本機資料備份，必須先驗證再升級。
3. **需保守处理**：PWA 快取、MCP 協定、可選外部 CLI 都不得因升級而破壞舊客戶端。
4. **不需現在做**：不引入 pip 套件、不建立前端 build pipeline、不自動升級外部正式服務。
