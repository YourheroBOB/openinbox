# Openinbox 執行手冊（RUNBOOK）

本文件說明如何在乾淨的 checkout 上安裝、啟動、測試與除錯 openinbox，並列出常見故障的處理順序。所有指令與行為都以目前程式為準：`install.sh`、`run.sh`、`server/app.py`、`server/mcp_server.py`、`scripts/smoke.sh`、`tests/`。文件中不出現任何真實憑證；需要示意值時一律使用 `FAKE_VALUE_FOR_TEST` 這類明顯假字串。

> 本手冊只涵蓋「本機／單機」操作。專案沒有公開部署模式，服務只監聽 `127.0.0.1`，對外一律走 SSH 本機轉發。

---

## 1. 前置條件

| 需求 | 說明 | 缺少時 |
|---|---|---|
| Python 3.9 以上 | 伺服器、SQLite、MCP、所有本機工具 | `install.sh` 直接結束（exit 1） |
| Bash 相容 shell | `install.sh`、`run.sh`、`scripts/smoke.sh` | 可手動 `python3 server/app.py`，但不建議取代標準流程 |
| 現代瀏覽器 | 面板、PWA、桌面通知 | HTTP API 與 MCP 仍可用 |
| Node.js（選用） | 只給部分 UI 測試做 `node --check` 語法檢查 | 相關 UI 測試會跳過，不影響 Python 核心 |
| SQLite FTS5（選用） | 全文搜尋效能 | 自動退回 `LIKE`，結果正確但大資料集較慢 |

不需要 pip、npm、Redis、外部資料庫或 SMTP 服務。**不要**為了跑起來而 `pip install` 任何東西。

---

## 2. 安裝

```bash
git clone https://github.com/YourheroBOB/openinbox.git
cd openinbox
./install.sh
```

`install.sh` 的實際行為，依序是：

1. 檢查 `python3` 是否存在；不存在就印出 `Need python3 3.9+` 並結束。
2. 以 Python 檢查版本是否低於 3.9；低於就結束，否則印出目前版本。
3. `mkdir -p data vault/cards`。
4. `accounts.json` **不存在時**才從 `accounts.example.json` 複製。
5. `agent.json` **不存在時**才從 `agent.example.json` 複製。

因此重複執行安裝是安全的，**不會覆寫你已經改過的設定檔**。

安裝後預期看到：

```bash
ls -1 accounts.json agent.json
ls -d data vault/cards
```

`accounts.json` 預設是 `"mode": "demo"`，第一次啟動會載入 `fixtures/` 的虛構示範信件，不需要任何信箱帳號。

---

## 3. 啟動

```bash
./run.sh
```

`run.sh` 會：

1. 切到 repo 根目錄。
2. `accounts.json` 不存在時先執行 `./install.sh`。
3. 設定 `OPENINBOX_ROOT` 為 repo 根目錄。
4. 設定 `OPENINBOX_PORT`（預設 `8770`，可用環境變數覆寫）。
5. `exec python3 server/app.py`（前景執行）。

啟動後開 <http://127.0.0.1:8770/>。

### 3.1 常用啟動變化

```bash
# 換埠（例如 8770 已被占用）
OPENINBOX_PORT=8771 ./run.sh

# 遠端主機或不想自動開瀏覽器
OPENINBOX_NO_BROWSER=1 ./run.sh

# 常駐（建議用 tmux／screen，不要自己改綁定位址）
tmux new -s openinbox 'OPENINBOX_NO_BROWSER=1 ./run.sh'
```

環境變數一覽（目前程式實際會讀的）：

| 變數 | 預設 | 用途 |
|---|---|---|
| `OPENINBOX_ROOT` | `run.sh` 自動設為 repo 根 | 決定資料目錄基準，MCP 也用同一個變數 |
| `OPENINBOX_PORT` | `8770` | HTTP 監聽埠，仍只綁 `127.0.0.1` |
| `OPENINBOX_NO_BROWSER` | 未設 | 設為 1 時不自動開瀏覽器 |
| `TPI_IMAP_PASSWORD_*` | 無 | IMAP 密碼來源，見 4.2 |

### 3.2 啟動後的第一個檢查

```bash
curl -s http://127.0.0.1:8770/api/health
```

回傳正常 JSON 即代表 HTTP 層、資料庫與功能載入都起來了。

---

## 4. 設定

### 4.1 `accounts.json`（郵件來源）

預設 demo 模式。要接真信箱時改成 live，例如：

```json
{
  "mode": "live",
  "accounts": [
    { "email": "you@example.com", "platform": "gmail", "driver": "gog", "label": "Work" },
    { "email": "me@example.com", "driver": "imap", "provider": "icloud", "label": "iCloud",
      "password_env": "TPI_IMAP_ICLOUD_PASSWORD" }
  ]
}
```

驅動差異：

- `demo`：只讀本機 `fixtures/`，零網路。
- `gog`：Gmail，透過外部 `gog` CLI。
- `gsk`：額外 IMAP／Outlook，透過 CLI 的信件 API（只做傳輸）。
- `imap`：標準函式庫 `imaplib`，**唯讀**：以 `EXAMINE` 開信箱、`BODY.PEEK` 取信，不改遠端任何狀態。

改完設定後在面板按「重新整理」，或重啟服務。

### 4.2 IMAP 密碼（只看環境變數）

密碼來源只有兩條，優先序如下：

1. 帳號設定裡的 `password_env` 指名的環境變數。
2. 否則讀 `TPI_IMAP_PASSWORD_<信箱大寫、非英數字換成 _>`。

```bash
# 示意用法，值一律用明顯假字串
export TPI_IMAP_ICLOUD_PASSWORD='FAKE_VALUE_FOR_TEST'
OPENINBOX_NO_BROWSER=1 ./run.sh
```

規則與注意事項：

- `accounts.json` 裡若出現明文 `password`，會被拒絕。
- 不要把密碼寫進任何檔案、commit 內容或 shell 歷史。用完就 `unset`。
- iCloud 需要 App 專用密碼，不是 Apple ID 主密碼。
- 驗證單一帳號是否可連線（只登入＋`EXAMINE`，不下載）：

```bash
curl -s -X POST http://127.0.0.1:8770/api/providers/check \
  -H 'Content-Type: application/json' -d '{"email":"me@example.com"}'
curl -s http://127.0.0.1:8770/api/providers
```

`/api/providers` 只回環境變數**名稱**、各帳號信件數與上次同步結果，不會回密碼。

### 4.3 `agent.json`（自帶 Agent）

四種驅動：`local`（內建啟發式，零網路，永遠可用當後備）、`openai_compatible`、`cli`、`http`。

```json
{
  "driver": "openai_compatible",
  "openai_compatible": {
    "base_url": "http://127.0.0.1:11434/v1",
    "model": "llama3.1",
    "api_key_env": "OPENAI_API_KEY"
  }
}
```

- 金鑰一律用 `api_key_env` 指向環境變數，不要直接寫進 JSON。
- 外部 Agent 會收到 context pack（人格、近期信件片段、規則等），**這就是資料外送**，啟用前要想清楚。
- 未接或呼叫失敗時，功能會退回本機啟發式並在回應標示 fallback。驗證 fallback 最安全的方式：把 `base_url` 指向一個沒有服務的 loopback 埠，確認 UI 仍可用且標示「已退回本機」。

---

## 5. 測試

```bash
python3 -m unittest discover -s tests
scripts/smoke.sh
```

- `python3 -m unittest discover -s tests`：標準函式庫 unittest，涵蓋核心、外掛、MCP stdio、HTTP 端點與多個功能的 UI／API 契約。
- `scripts/smoke.sh`：以 Linux 本機、隨機埠啟動服務後做端到端 HTTP 檢查，與 CI 的 smoke 流程一致。

### 5.1 執行測試前務必知道的事

測試**不是**完全隔離在 repo 之外的沙箱，這點依實際測試碼：

- 多個測試工具檔（例如 `tests/_tpi_compose_util.py`、`tests/_tpi_brain_util.py`、`tests/_tpi_outbox_util.py`）會在 **repo 根目錄**建立／刪除暫存的 `agent.json`，並直接操作 `data/` 下的 SQLite（清表、重播示範資料）。
- 因此請在**乾淨 clone 或專用工作目錄**跑測試；不要在你平常使用、已同步真實信件快取的那份 checkout 上跑。
- 測試全部使用虛構資料與假 Agent（用 `python3 -c` 組出的本機 CLI 假 agent）。不要在測試中指向正式 IMAP、正式模型端點或正式 CLI。
- 部分 UI 測試需要 Node.js；沒有 Node 時那些測試會跳過，Python 核心測試不受影響。
- MCP 測試以 stdio 直接啟動 `server/mcp_server.py`，不需要先開網頁面板。

---

## 6. MCP 伺服器（stdio）

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{}}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python3 server/mcp_server.py
```

- 一行一則 JSON-RPC 2.0 訊息；支援 `initialize`、`tools/list`、`tools/call`、`ping`。
- 工具：`list_inbox`、`brain_board`、`search_brain`、`persona`、`save_draft`。
- 前四項只讀本機快取；`save_draft` 只寫本機 SQLite 草稿表，**不會寄出**。
- `OPENINBOX_ROOT` 可省略（預設為 checkout 根）。若你要讓 MCP 指向別的資料目錄，請設這個變數。
- Claude Desktop／Cursor 的設定片段見 `README.md`，把路徑換成你的 checkout 即可。不需要先啟動網頁面板。

除錯重點：MCP 走 stdio，**任何寫到 stdout 的非 JSON 內容都會破壞協定**。若客戶端連不上，先把上面那段 `printf | python3` 在本機跑一次，確認 stdout 乾淨。

---

## 7. 日常健檢清單（唯讀）

依序執行，可快速判斷問題落在哪一層：

```bash
curl -s http://127.0.0.1:8770/api/health        # 服務活著嗎
curl -s http://127.0.0.1:8770/api/features     # 外掛載入狀況與匯入錯誤
curl -s http://127.0.0.1:8770/api/ui-modules    # UI 模組清單
curl -s http://127.0.0.1:8770/api/cache         # 目前快取了什麼
curl -s http://127.0.0.1:8770/api/providers     # 帳號、信件數、上次同步結果
curl -s http://127.0.0.1:8770/api/usage         # BYOK token 用量（不含提示詞／回答）
curl -s http://127.0.0.1:8770/api/skills        # 技能清單與開關
curl -s http://127.0.0.1:8770/api/mobile/info   # service worker 實際快取的靜態檔
```

`/api/features` 是外掛問題的第一站：它會列出已載入功能、路由與匯入錯誤。錯誤訊息不含郵件內容與憑證。

---

## 8. 除錯

### 8.1 服務起不來

1. `python3 --version`：必須 3.9 以上。
2. `./install.sh` 是否曾中斷：確認 `accounts.json`、`agent.json`、`data/`、`vault/cards/` 都在。
3. 直接前景執行看完整錯誤：`OPENINBOX_NO_BROWSER=1 python3 server/app.py`。
4. 埠占用：`ss -ltnp | grep 8770` 或 `lsof -i :8770`；改用 `OPENINBOX_PORT=8771 ./run.sh`。

### 8.2 收件匣是空的

- demo 模式第一次啟動才會播種示範信。若你清過快取，需要重新播種：

```bash
curl -s -X POST http://127.0.0.1:8770/api/cache/clear \
  -H 'Content-Type: application/json' -d '{"reseed": true}'
```

- live 模式請確認 `accounts.json` 的 `mode`、帳號與驅動正確，並看 `/api/providers` 的錯誤欄位。

### 8.3 功能沒出現、面板少一塊

1. `GET /api/features`：是否列出該功能、是否有 import error。
2. `GET /api/ui-modules`：對應的 `ui/modules/*.js` 是否有被列出。
3. 外掛是在主程序內直接載入的 Python 檔案；語法錯誤會讓該功能整個不載入，但其他功能應維持運作。
4. 前端錯誤請開瀏覽器開發者工具的 Console；UI 字串必須同時有繁中與英文。

### 8.4 搜尋很慢或結果不對

- 搜尋優先用 FTS5 索引；若目前 Python 的 SQLite 沒有 FTS5，會整體退回 `LIKE`，結果仍正確但速度較慢。
- 需要重建索引時呼叫 `/api/search/reindex`（唯讀重建、不動遠端信箱）。
- 搜不到剛同步的信：先確認 `/api/providers` 顯示同步成功，再看 `/api/cache`。

### 8.5 Agent 沒生效或結果像罐頭

1. 確認 `agent.json` 的 `driver` 與對應區塊完整。
2. 回應若帶 fallback 標示，代表外部 Agent 逾時、錯誤或回傳空白，系統已退回本機啟發式。
3. 錯誤訊息只會保留例外類別與 HTTP 狀態碼，不會回傳外部端點原始回應或提示詞 —— 這是預期行為，不要為了「看清楚」而把原始 body 印出來。
4. 驗證流程最安全的做法：先把驅動指到本機不存在的位址，確認 fallback 正常，再接真服務。

### 8.6 IMAP 連線失敗

| 訊息型態 | 檢查 |
|---|---|
| 缺少密碼 | 對應的 `password_env` 或 `TPI_IMAP_PASSWORD_*` 是否已 `export`（名稱大小寫、非英數字換成 `_`） |
| CLI 不存在／認證失敗 | `gog`／`gsk` 是否安裝、是否已完成該 CLI 自己的登入 |
| 網路或 TLS 失敗 | host／port／`security` 設定；`security: none` 只允許 loopback |
| 帳號被拒 | App 專用密碼、兩階段驗證設定 |

先跑 `POST /api/providers/check`（只登入＋`EXAMINE`），再做完整同步，避免一次拉大量資料。單一帳號失敗不應影響其他帳號。

### 8.7 成果卡片（Agent 協作）打不開

- `/api/agents/deliverables/<id>.<fmt>`：`fmt` 只接受 `md`、`html`、`json`，`id` 需符合嚴格格式，否則回 404。
- 成果檔案在 `data/deliverables/`；若整個目錄被刪，列表會是空的但不會報錯。
- HTML 卡片會把所有內容轉義、不含 script 與外部資源，前端以 sandbox iframe 預覽 —— 這是刻意設計，不要改成放寬。

### 8.8 PWA／離線頁行為異常

- service worker 只在 HTTPS 或 `127.0.0.1` 生效。
- 它只快取離線頁、manifest、圖示與 `ui/modules/*.js`，**完全不碰 `/api/*`**，所以瀏覽器裡不存信件。
- 行為不符預期時用 `GET /api/mobile/info` 對照實際快取清單，再做一次硬重新整理。

### 8.9 變更資料的端點回 403

`features/_origin.py` 會檢查請求是否來自主機自身來源；從其他來源（或缺少正確 Origin）發出的變更請求會被拒絕。這是防護，不是 bug。需要操作時請在 `127.0.0.1` 上以瀏覽器或 `curl` 執行。

---

## 9. 維運

### 9.1 清除本機快取

```bash
curl -s http://127.0.0.1:8770/api/cache
curl -s -X POST http://127.0.0.1:8770/api/cache/clear \
  -H 'Content-Type: application/json' -d '{}'
```

清除語意：

- **會清**：郵件快取、示範／快取行事曆、Agent 回合結果（含 triage 相關快取）、衍生卡片與衍生人格／索引。
- **會保留**：草稿、你自己寫的筆記卡、本機建立或匯入的行事曆資料、邀請草稿與匯入 feed（`cal_feeds`）。
- `{"reseed": true}` 會重新載入虛構示範信件。

這是資料隔離操作，**不是備份或還原機制**。

### 9.2 備份（目前沒有內建流程）

程式尚未提供備份與還原指令。保守做法：

1. 停止服務（避免複製到寫入中的 SQLite）。
2. 備份 `data/`、`vault/`、`accounts.json`、`agent.json`。
3. 若一定要在服務執行中備份，使用 SQLite 的備份機制，不要直接 `cp` 使用中的 `.db`：

```bash
python3 - <<'PY'
import sqlite3
src = sqlite3.connect("data/openinbox.db")
dst = sqlite3.connect("backup-openinbox.db")
with dst:
    src.backup(dst)
dst.close(); src.close()
print("ok")
PY
```

4. 需要時檢查完整性（不依賴外部 sqlite3 CLI）：

```bash
python3 -c "import sqlite3;print(sqlite3.connect('data/openinbox.db').execute('PRAGMA integrity_check').fetchone()[0])"
```

備份檔含郵件內容與帳號中繼資料，請比照信箱等級保護：加密磁碟、限制權限、不要放進任何同步或雲端資料夾。備份內容**不含**任何憑證值（憑證只在環境變數），但 `accounts.json` 會有帳號地址等中繼資料。

### 9.3 資料位置速查

| 路徑 | 內容 | 是否進 git |
|---|---|---|
| `data/openinbox.db` | 郵件快取、草稿、行事曆、outbox、搜尋索引等 | 否（`data/` 已忽略） |
| `data/deliverables/` | Agent 協作成果（md／html／json） | 否 |
| `data/slides/` | 技能產生的本機 HTML 投影片 | 否 |
| `data/contacts.json` | 本機 CRM 聯絡人 | 否 |
| `data/skills.json` | 技能開關 | 否 |
| `data/usage.jsonl` | BYOK token 用量（無提示詞、回答、金鑰） | 否 |
| `vault/persona.json`、`vault/persona.md` | 人格檔 | 否 |
| `vault/index.json` | Second Brain 索引 | 否 |
| `vault/cards/*.md` | 卡片與你的筆記 | 否（只保留 `.gitkeep`） |
| `accounts.json`、`agent.json`、`rules.json` | 本機設定 | 否 |

---

## 10. 遠端主機（雲端 Linux）

伺服器只聽 `127.0.0.1:8770`，因此遠端主機**不要**開對外埠、不要架反向代理。

主機上：

```bash
git clone https://github.com/YourheroBOB/openinbox.git && cd openinbox
./install.sh
OPENINBOX_NO_BROWSER=1 ./run.sh     # 建議放進 tmux／screen
```

筆電上：

```bash
ssh -N -L 8770:127.0.0.1:8770 user@your-host.example.com
```

本機開 <http://127.0.0.1:8770/>。筆電的 8770 被占用就改用 `-L 8771:127.0.0.1:8770` 再開 8771。主機防火牆請保持關閉 8770。`accounts.json`、`agent.json`、`data/`、`vault/` 都在主機上，那顆磁碟要當成你的信箱來保護。

手機同理：用 SSH App 轉送同一個埠，再開 `http://127.0.0.1:8770/`。

---

## 11. 安全紅線（做任何事之前先看）

1. 不要把任何 token、金鑰、密碼、客戶個資、信件內文或案件當事人資料寫進 repo、issue、log 或文件。
2. 不要修改 `.github/workflows/`、secrets／憑證設定、git remote 或部署流程。
3. 不要讓服務綁到 `0.0.0.0`；對外一律 SSH 通道。
4. 不要在自動測試中連線正式 IMAP、正式模型端點或任何網路上的正式服務。測試憑證只用 `FAKE_VALUE_FOR_TEST` 這類假值。
5. 測試與腳本只讀寫 repo 內路徑或系統暫存目錄（`tempfile`／`tmp_path`）。
6. `save_draft` 是唯一寫入工具；沒有任何 Agent 工具可以寄信。不要自己開後門。
7. Python 外掛是**受信任的本機程式碼**，不是沙箱。載入來源不明的 `server/features/*.py` 等同賦予本機檔案權限。
8. 不要把郵件主旨、寄件人、內文貼進錯誤訊息或除錯輸出；既有程式刻意只保留例外類別與 HTTP 狀態碼。

---

## 12. 已知限制（除錯時不要誤判為 bug）

1. 沒有內建備份／還原與版本化遷移工具。
2. 資料庫與 vault 沒有透明加密，保護責任在檔案系統權限與磁碟加密。
3. outbox 只做排程、確認、倒數取消與本機 EML 匯出，**不是寄信服務**。
4. 單機、單程序設計；高併發寫入與多使用者不是目標。
5. 外部 CLI（`gog`、`gsk`、自訂 Agent CLI）行為依版本而異，需以本機整合測試與明確版本假設維護。
6. 郵件內容變更後，舊摘要／卡片何時失效尚未形成完整一致性契約（見 `docs/fmb/ROADMAP.md` 第 2 項）。
