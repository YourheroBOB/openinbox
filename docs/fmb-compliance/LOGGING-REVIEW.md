# 記錄檔與錯誤訊息外洩欄位盤點

本文件盤點 openinbox 可能產生記錄的位置、其中可能含有的個資欄位，並提出遮罩與測試建議。

## 1. 原則

1. **記錄事件，不記錄內容**：記錄「同步失敗（帳號 A）、錯誤類型 `IMAP4.error`」即可，不需要主旨或內文。
2. **識別碼優於值**：用不透明的 `email_id`、`thread_id`，不要用寄件人 Email 或姓名。
3. **錯誤訊息白名單**：只輸出例外類別與必要狀態碼；不輸出外部端點回應或 CLI stderr 原文。
4. **日誌本身也是個資檔案**：需有保存期限與檔案權限（建議 `600`）。

## 2. 現有良好實務（可直接沿用）

| 實務 | 位置 | 說明 | 證據 |
|---|---|---|---|
| 錯誤只保留例外類型與 HTTP 狀態 | `server/features/agents.py` `error_label()` | 明確註解「agent_bridge 的錯誤可能含端點回應或 CLI 對提示詞的 stderr 回顯」，因此只回 `Type: HTTP nnn` | `[A]` |
| 用量檔不記提示詞、回答、金鑰 | `data/usage.jsonl` | README 明示只記 token 數 | `[A]` README |
| 帳號 API 只回環境變數名稱 | `GET /api/providers` | 不回傳密碼值 | `[A]` README |
| 明文 `password` 在 `accounts.json` 會被拒絕 | `accounts.json` 讀取邏輯 | 強制憑證只從環境變數 | `[A]` README |
| Service worker 不快取 `/api/*` | `ui/pwa/sw.js`（由 `mobile.py` 提供） | 瀏覽器端不殘留郵件 | `[B]` |
| 成果 HTML 全轉義、sandbox iframe 預覽 | `agents.py` `_render_html()`、`agents.js` | 避免注入與外連 | `[A]` |

**建議**：把 `error_label()` 的模式提升為共用工具（例如 `server/logsafe.py`），讓所有模組統一呼叫，而不是各自處理。

## 3. 可能外洩的記錄點

| # | 記錄點 | 可能含有的個資 | 風險 | 現況 | 建議 |
|---|---|---|---|---|---|
| L1 | HTTP 伺服器請求記錄（`BaseHTTPRequestHandler.log_message` 會把請求行寫到 stderr） | 若未覆寫，`GET /api/...?q=王小明` 這類查詢字串（含姓名、主旨關鍵字、Email）會落到 stderr | **高** | `[C]` `server/app.py` 未在本輪可見範圍 | 覆寫 `log_message`：只記方法、路徑（去查詢字串）、狀態碼、耗時；或整批關閉並改結構化日誌 |
| L2 | 同步錯誤訊息（`LAST_SYNC`、`/api/providers`） | IMAP／CLI 回應可能含帳號、伺服器訊息、甚至寄件人字串 | 中高 | `[B]` 有遮罩密碼，但是否遮罩其他內容 `[C]` | 正規化為錯誤類別代碼；保留原始訊息於可選 debug 模式且需明確開啟 |
| L3 | BYO agent 錯誤 | `agent_bridge` 可能把端點回應 body 或 CLI stderr（含提示詞片段）帶進例外 | 中高 | `[A]` `agents.py` 已遮罩；其他呼叫端 `[C]` | 全面改用 `error_label()` 等效函式 |
| L4 | CLI 驅動的 stderr／stdout | 可能含 context pack 片段（郵件內容） | 中高 | `[C]` | 不落檔；若需除錯，只存去識別化後長度與雜湊 |
| L5 | `data/usage.jsonl` | token 數、時間；若額外寫 model／driver 則為低敏感中繼資料 | 低 | `[B]`／`[C]` 欄位需確認 | 明確固定欄位白名單並加測試 |
| L6 | 搜尋查詢 | 自然語言查詢常含人名、公司名、金額 | 中 | `[C]` | 不記錄查詢原文；若需改善搜尋品質，記錄「命中數」與「是否使用 Agent 改寫」 |
| L7 | 附件檔名 | 檔名常含人名、案號、身分證末碼 | 中 | `[C]` | 不記錄檔名；需要時記錄副檔名與大小 |
| L8 | 檔案路徑 | 可能含作業系統使用者名稱（`/home/<name>/openinbox/...`） | 低中 | `[A]` `/api/features` 有載入錯誤顯示 `[C]` | 顯示相對路徑 |
| L9 | `agent.json` 的 `base_url` | 可能揭露供應商、內部主機名稱、租戶 id | 低中 | `[A]` | 顯示時只顯示 scheme + host，必要時遮罩路徑 |
| L10 | 環境變數名稱（`password_env`、`api_key_env`） | 僅名稱，不含值 | 低 | `[A]` README | 保持只顯示名稱；禁止回傳值 |
| L11 | `scripts/overnight.py` 輸出 | 夜班 brief 可能含郵件原文 | 中高 | `[C]` | 輸出視為資料檔（權限 600、納入保留期與清除範圍），不可寫入 repo |
| L12 | `scripts/smoke.sh` 與 CI 日誌 | 測試失敗時可能 dump DB 內容或 context pack | 中 | `[C]` | 測試只使用 `fixtures/`；禁止 `print(request.body)`；CI 保留期由平台控制 |
| L13 | `state/*.md`、`STATE.md` 開發日誌 | 開發者可能貼上真實錯誤訊息或信件內容 | 中 | `[A]` 目前內容未見真實個資 | 在 `CONTRIBUTING` 加一條「不得貼入真實郵件或帳號」 |
| L14 | GitHub Actions 日誌 | 同上；repo 為私有，但日誌仍可能被保留與匯出 | 中 | `[C]` | 只跑 fixtures；避免 `set -x` 於含敏感變數的段落 |
| L15 | 瀏覽器 console | UI 若 `console.log(state)` 會把整封郵件寫進瀏覽器 console 與擴充套件 | 中 | `[C]` | 生產環境移除 debug logging，或加 `DEBUG` 旗標 |

## 4. 遮罩與欄位白名單建議

### 4.1 允許寫入日誌的欄位

`timestamp`、`level`、`event`（列舉字串）、`route`（去查詢字串）、`status`、`duration_ms`、`account_label`（使用者自訂標籤，非 Email；或 Email 的網域部分）、`error_class`、`http_status`、`count`。

### 4.2 禁止寫入日誌的欄位

`subject`、`body_text`、`snippet`、`from_addr`（完整）、`to_addr`（完整）、`attachment_name`、`query`、`prompt`、`answer`、`api_key`、`password`、`token`、`session`、`cookie`、`base_url` 完整路徑。

### 4.3 需要時的遮罩方式

| 值 | 建議處理 |
|---|---|
| Email | 只留網域：`***@example.com`；或 `sha256(value + salt)[:8]`（salt 存本機、不進日誌） |
| 姓名 | 不記錄；必要時只記「1 位寄件人」 |
| 金額 | 不記錄 |
| 路徑 | 相對路徑，去掉家目錄 |
| 端點 | scheme + host，去掉 path／query |

> 若引入雜湊遮罩，必須用固定 salt 且 salt 不落日誌；否則同一 Email 在不同環境會得到不同雜湊，反而無法比對。

## 5. 建議的結構化日誌規格（草案）

```
{
  "ts": "2026-01-01T00:00:00+08:00",
  "level": "info",
  "event": "sync.done",
  "route": null,
  "account": "demo-inbox",
  "count": 8,
  "duration_ms": 42,
  "error_class": null,
  "http_status": null
}
```

- 預設輸出到 stderr，由使用者自行導向檔案（權限應為 `600`）。
- 提供 `OPENINBOX_LOG_LEVEL`（`off`／`error`／`info`／`debug`），預設 `error`。
- `debug` 模式仍不得輸出禁止欄位，只增加事件類型。

## 6. 驗收測試建議

1. 以 `tmp_path` 建立資料目錄，放入假郵件（`alice@example.test`、主旨 `FAKE_SUBJECT_FOR_TEST`）。
2. 觸發同步錯誤、BYO agent 錯誤、搜尋、摘要、Agent 協作。
3. 擷取 stderr 與所有產生的檔案，斷言**不含** `FAKE_SUBJECT_FOR_TEST`、`alice@example.test`、`FAKE_VALUE_FOR_TEST`。
4. 斷言錯誤回應只含 `error_class` 與 `http_status`。
5. 斷言 `data/usage.jsonl` 只有白名單欄位。
6. UI 測試：以 CDP 開頁面後檢查 `console` 訊息不含郵件字串（`tests/_tpi_mobile_cdp.js` 已有 CDP 基礎）。

## 7. 對應缺口

| 缺口 | 說明 |
|---|---|
| G9 | 記錄與錯誤訊息可能外洩個資欄位 |
| G12 | 事故（外洩）通報流程未建立，日誌也無法支撐調查 |
| G6 | 日誌檔權限與保留期未定義 |
