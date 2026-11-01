# 驗證矩陣與回滾方式

本檔整理各階段共用的驗證與回滾原則。所有指令都應在暫存環境或本機 loopback 執行，不得連接正式外部服務。

## 1. 支援與驗證矩陣

| 層面 | 保守支援矩陣 | 驗證方式 |
|---|---|---|
| Python | 3.11、3.12、3.13 | `python3 -m unittest discover -s tests` |
| SQLite | 以目標機 `sqlite3.sqlite_version` 為準 | 備份、遷移 dry-run、數量檢查 |
| FTS5 | 有用：正常索引；沒有：回落 LIKE | 假資料比對兩路搜尋結果 |
| Bash | 未確認 install.sh 需求前，不假定 Bash 4+ | `bash -n`、乾淨暫存安裝 |
| Node.js | 選擇性；只用於 JS 語法檢查 | `node --check ui/modules/*.js` |
| 瀏覽器 | Chrome、Edge、Firefox、Safari 近代版本 | 面板、PWA、service worker、離線頁 |
| MCP | 現有協定 `2025-06-18` 相容 | 假 stdio 客戶端 |
| 外部 Agent | 不自動升級；只測 fake | 逾時、錯誤、fallback |

## 2. 核心驗證指令

```bash
git status --short
python3 -m unittest discover -s tests
scripts/smoke.sh
bash -n run.sh install.sh scripts/smoke.sh
node --check ui/modules/*.js || true
```

Python 語法檢查避免污染 repo：

```bash
PYTHONPYCACHEPREFIX="$(mktemp -d)" python3 -m compileall -q server tests
```

FTS5 可用性：

```bash
python3 - <<'PY'
import sqlite3
con = sqlite3.connect(":memory:")
try:
    con.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
    print("fts5=yes")
except sqlite3.OperationalError as e:
    print("fts5=no", type(e).__name__)
PY
```

本機服務啟動 smoke：

```bash
OPENINBOX_NO_BROWSER=1 OPENINBOX_PORT=18770 ./run.sh
```

## 3. 資料安全驗證

任何涉及 SQLite、搜尋索引、衍生資料的階段，都要先做備份。

```bash
python3 - <<'PY'
import pathlib, sqlite3, tempfile
src = pathlib.Path("data/openinbox.db")
if not src.exists():
    print("no-local-db-skip")
    raise SystemExit(0)
tmp = pathlib.Path(tempfile.gettempdir()) / "openinbox-upgrade-check.db"
with sqlite3.connect(src) as s, sqlite3.connect(tmp) as d:
    s.backup(d)
print("backup-ok", tmp)
PY
```

驗證備份：

```bash
python3 - <<'PY'
import pathlib, sqlite3, tempfile
backup = pathlib.Path(tempfile.gettempdir()) / "openinbox-upgrade-check.db"
if not backup.exists():
    print("no-backup-skip")
    raise SystemExit(0)
con = sqlite3.connect(backup)
print("integrity", con.execute("PRAGMA integrity_check").fetchone())
con.close()
PY
```

檢查清單：

- 郵件、草稿、聯絡人、技能設定、卡片數量是否符合升級前後預期。
- 清除快取後可重生，但不刪除使用者手寫卡片。
- 還原預設 dry-run，不直接覆蓋正式 `data/`。
- manifest 與日誌不含郵件內文、寄件人、案件資料、金鑰或密碼。

## 4. 回滾原則

| 階段 | 回滾方式 | 資料處理 |
|---|---|---|
| 階段 0 文件 | 捨棄文件 commit | 無影響 |
| 階段 1 Python 政策 | 回復版本字串與 install.sh／CI 設定 | 無資料異動 |
| 階段 2 相容性修正 | 回復程式 commit | 原則上無 schema 異動 |
| 階段 3 SQLite／FTS5 | 回復遷移與索引程式；必要時還原備份 | 先 dry-run，再覆寫 |
| 階段 4 PWA／UI | 回復 UI／service worker；提升快取版本 | 只影響瀏覽器快取 |
| 階段 5 MCP／外部驅動 | 回復協定與驅動程式；保留舊工具 | 不還原資料庫 |
| 階段 6 上線演練 | 回復穩定 commit；重跑 smoke | 必要時還原 `data/`、`vault/` |

## 5. 回滾演練最低要求

1. 在暫存根目錄完成一次「升級 → 驗證 → 回滾 → 驗證」。
2. 確認回滾後核心 API 可開、收件匣可讀、搜尋可用、草稿保留。
3. 確認回滾過程沒有連線正式 IMAP、Agent、ICS 或 MCP 正式服務。
4. 確認回滾文件與日誌沒有敏感資料。

## 6. 預期測試結果

- 本任務只新增 `docs/fmb-upgrade/` Markdown，未修改產品碼，因此預期既有 `unittest` 與 smoke 不受影響。
- 實際升級階段需由後續 PR 執行，並在該 PR 記錄真實測試結果，不可只引用本文件。
