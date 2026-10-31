# fmb_examples — 可直接執行的離線範例

這個目錄只放**使用範例**，示範 openinbox（TooPowerInbox）幾個對外介面怎麼用：
MCP over stdio、thread 裡的 `@agent` 提及路由、Agent 成果卡片、本機 HTTP API、
以及 IMAP 設定的離線預檢。

- 只新增 `fmb_examples/` 底下的檔案；沒有修改 `server/`、`ui/`、`tests/`、
  `.github/workflows/` 或任何既有檔案。
- 全部離線可跑：只用 Python 標準函式庫，不連外網、不需要真實信箱、不需要模型或金鑰。
- 需要設定值的地方一律用明顯假值（`FAKE_VALUE_FOR_TEST`、`you@example.com`、
  `imap.example.com`）；密碼只用**環境變數名稱**表示，不寫任何憑證值。

## 需求

| 項目 | 需求 |
|---|---|
| Python | 3.9 以上（與主程式相同） |
| 套件 | 無。不需要 `pip`、`npm`、Node.js |
| 網路 | 不需要。唯一的連線是 `127.0.0.1` 上由範例 04 自己起、自己關的本機伺服器 |
| 信箱／金鑰 | 不需要。demo 模式與假資料即可 |

## 檔案

| 檔案 | 作用 |
|---|---|
| `examples.py` | 五個範例的實作與入口（`ex01`～`ex05`） |
| `_harness.py` | 共用沙箱、子程序環境、檢查結果收集（`Checks`） |
| `README.md` | 本文件 |

## 執行

```bash
python3 fmb_examples/examples.py            # 依序跑完五個範例，最後印 summary
python3 fmb_examples/examples.py 03         # 只跑 03
python3 fmb_examples/examples.py 01 04      # 只跑 01 與 04
python3 fmb_examples/examples.py mcp_stdio_smoke   # 也可以用短名
```

結束碼：`0` 表示核心檢查全部通過；`1` 表示有檢查失敗（會列出是哪幾項）；`2` 是參數錯誤。
若某個模組不在這個 checkout，該範例會印 `SKIP:` 並以 `0` 結束——跳過不算失敗。

## 沙箱：範例在哪裡跑

`_harness.py` 會把這個 repo **複製到系統暫存目錄的一次性副本**，所有讀寫都只在副本裡：

- 不複製 `accounts.json`、`agent.json`、`rules.json`、`.env*`、`data/`、`vault/`、`*.db`、
  `__pycache__/`，所以真實帳號設定、信件快取與草稿不可能進到副本。
- 副本缺設定檔時，從 `accounts.example.json` / `agent.example.json` 產生
  （`mode: demo`、`driver: local`），因此不會有對外連線。
- 子程序一律帶 `OPENINBOX_ROOT`、`OPENINBOX_NO_BROWSER=1`，並以副本為工作目錄。
- 範例不會把沙箱指到 repo 本身或 repo 內的目錄（會被拒絕）。
- 跑完自動刪除副本。想留下來檢查：先 `export FMB_EXAMPLE_ROOT=/tmp/fmb-inspect`
  （此目錄不會被自動刪除）。

## 五個範例

| # | 示範什麼 | 會寫入什麼 |
|---|---|---|
| 01 | stdio MCP：`initialize` → `tools/list` → `tools/call`（`list_inbox`、`persona`）→ `ping` → 未知工具 | 只在副本播種 demo 快取（唯讀工具） |
| 02 | `parse_mention()` / `error_label()`：`@agent`、`@research`、`@research-company`、`@prep` 的解析與錯誤訊息收斂 | 無（純函式） |
| 03 | `save_deliverable()`：Markdown ＋ 轉義 HTML 寫入後讀回，並驗證路徑穿越／不合法 id 被拒 | 副本的 `data/deliverables/` |
| 04 | 起本機面板，讀 `/api/health`、`/api/inbox`、`/api/providers`，只印狀態碼、鍵名與數量 | 副本的 `data/openinbox.db` |
| 05 | `fmb_feature2/imap_mailbox.audit_accounts()`：全假帳號設定的離線預檢（不登入） | 無 |

### 01 — MCP over stdio

`python3 server/mcp_server.py`（JSON-RPC 2.0、一行一則訊息）。送出的請求是固定的六個，
輸出只印「成功與否、工具名稱、字元數、結束碼」，**不印任何信件內容**。
**不呼叫 `save_draft`**：那是唯一會寫入本機草稿表的工具，範例不需要它。

預期輸出（數字依 fixtures 而定）：

```
sandbox: /tmp/fmb-openinbox-xxxxxxxx
=== 01 mcp_stdio_smoke — MCP over stdio：…
   [ok] 1. initialize — protocolVersion='2025-06-18'
   [ok] 2. tools/list — 5 tool(s): list_inbox, brain_board, search_brain, persona, save_draft
   [ok] 3. tools/call list_inbox（唯讀） — N chars（內容不列印）
   [ok] 4. tools/call persona（唯讀） — N chars
   [ok] 5. ping
   [ok] 6. 未知工具被擋下且伺服器不崩潰 — exit=0
PASS: mcp_stdio_smoke
```

### 02 — `@agent` 提及 → 任務

直接呼叫 `features.agents.parse_mention()` 與 `error_label()`，不碰資料庫、不寄任何東西。
這說明了面板為什麼「打 `@agent` 才觸發、一般訊息不觸發」，以及錯誤訊息為什麼只留例外類型
與 HTTP 狀態碼，不會把外部端點回應或 CLI stderr 帶回畫面。

預期輸出（節錄）：

```
   [ok] 1. @research Samira Ortiz 上週的往來重點 — kind=research_person target='Samira Ortiz 上週的往來重點'
   [ok] 2. @agent 幫我準備 Northwind partner office h… — kind=meeting_prep target='準備 Northwind …'
   [ok] 3. @agent Acme Corp 最近動態 — kind=research_company target='Acme Corp 最近動態'
   [ok] 4. @research-company Byte Cloud 的合約狀況 — kind=research_company target='Byte Cloud 的合約狀況'
   [ok] 5. @agent Pat Example — kind=research_person target='Pat Example'
   [ok] 6. @agent — kind=research_person target=''
   [ok] 7. 一般訊息不觸發（triggered=False）
   [ok] 8. error_label 保留 HTTP 狀態碼 — FakeHTTPError: HTTP 503
   [ok] 9. error_label 從訊息抓到狀態碼但丟掉本文 — FakeRemoteError: HTTP 429
   [ok] 10. error_label 只留例外類型 — ConnectionError
```

### 03 — 成果卡片（MD ＋ 轉義 HTML）

餵一個固定形狀的本機結果 dict 給 `save_deliverable()`（與本機啟發式回傳的形狀相同），
不需要接 Agent，也不需要信件快取。卡片文字裡刻意放了 `<script>…</script>`，
示範 HTML 一定轉義、不含外部資源；`read_deliverable("../accounts", …)` 這類 id 會被擋下。

預期輸出（節錄）：

```
   [ok] 成果卡片目錄落在沙箱內 — …/data/deliverables
   [ok] save_deliverable 產生合法 id — meeting-prep-pat-example-…
   [ok] list_deliverables 看得到新卡片 — 1 card(s)
   [ok] 讀回 .md — text/markdown; charset=utf-8
   [ok] md 以卡片標題開頭 — # 會議準備：Pat Example
   [ok] 讀回 .html — text/html; charset=utf-8
   [ok] HTML 轉義 script
   [ok] HTML 無遠端資源
   [ok] 路徑穿越被拒（../accounts）
   [ok] 萬用字元被拒（*）
PASS: deliverable_card
```

### 04 — 本機 HTTP API（只印數量）

自己挑一個免費的 loopback 埠，以 `OPENINBOX_PORT` 起 `server/app.py`
（`OPENINBOX_NO_BROWSER=1`，不會開瀏覽器），讀三個端點後關掉伺服器。
`urllib` 已關閉 proxy，請求只會到 `127.0.0.1`；輸出只有狀態碼、鍵名與筆數。

預期輸出：

```
   starting server on 127.0.0.1:54321 (loopback only, no browser)
   [ok] GET /api/health -> 200 — keys=[…]
   [ok] GET /api/inbox -> 200 — items=8 keys=[…]
   [ok] GET /api/providers -> 200 — items=1 keys=[…]
PASS: http_inbox_counts
```

### 05 — IMAP 設定預檢（離線）

對一份手寫的全假設定呼叫 `fmb_feature2/imap_mailbox.py` 的 `audit_accounts()`：

```json
{
  "mode": "live",
  "accounts": [
    {"email": "you@example.com", "driver": "demo", "label": "Demo inbox"},
    {"email": "me@example.com", "driver": "imap", "provider": "icloud",
     "password_env": "TPI_IMAP_FAKE_PASSWORD", "mailbox": "收件匣"},
    {"email": "work@example.com", "driver": "imap", "host": "imap.example.com",
     "port": 993, "security": "ssl", "mailbox": "Archive/2026"}
  ]
}
```

重點：**只描述設定，不登入、不開信箱、不修改伺服器狀態**；密碼只以環境變數名稱表示
（`TPI_IMAP_FAKE_PASSWORD`，值不存在也不需要存在）。輸出會印頂層鍵、每個帳號的
`mailbox`／wire 形式／`password_env`／警告。若這個 checkout 沒有 `imap_mailbox.py`
或它的函式簽章不同，範例會印 `SKIP:` 並以 `0` 結束。

## 常見問題

- **`SKIP:` 是什麼意思？** 該模組不在這個 checkout，或匯入失敗；不是測試失敗，也不是產品問題。
- **會寄信嗎？** 不會。範例沒有任何寄信路徑；`save_draft` 也沒有被呼叫。
- **會印出信件內容嗎？** 不會。只印狀態碼、鍵名、數量、型別與字元數。
- **可以拿真實帳號試嗎？** 不要。範例刻意不讀真實設定；要接真信箱請照主 `README.md` 的說明，
  並把密碼放在環境變數。
- **範例依賴內部函式，改版會不會壞？** 會。這些是「使用示範」，不是穩定 API 契約；
  模組改名時範例會直接 `SKIP` 而非誤判成功。
