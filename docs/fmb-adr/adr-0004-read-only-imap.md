# ADR-0004：唯讀 IMAP——EXAMINE 與 BODY.PEEK

- 狀態：已接受（現況仍有效）
- 日期：事後補建（原始決策日未記錄）
- 影響範圍：`server/features/imap.py`、`providers.py`、`yhbmail.py` 同步路徑
- 相關：ADR-0006、ADR-0008；ROADMAP 第 3、5 項

## 背景

同步外部信箱時，最常見的副作用是「順手」在伺服器上標已讀、移動或刪除。對使用者而言，
已讀與否是個人行為，不該被同步程式決定；對帳號安全而言，寫入命令放大憑證洩漏時的傷害。

## 決策

1. IMAP 只用標準函式庫 `imaplib`，以 **`EXAMINE`**（唯讀模式）開啟信箱。
2. 抓信只用 **`BODY.PEEK`**，不設 `\Seen`——伺服器上什麼都不改，連已讀旗標都不動。
3. 連線安全：預設 993 SSL；`security` 可為 `starttls`；`none` 只允許本機 loopback。
4. `provider` 內建 `icloud`、`fastmail`、`yahoo`、`zoho` 預設值；其他信箱自訂 `host`／`port`；
   可用 `username`、`mailbox`（預設 `INBOX`）。
5. 「測試連線」（`POST /api/providers/check`）只做登入＋`EXAMINE`，不抓內容。
6. 已讀、星號、封存等本機狀態放在 `mail_state` 覆寫，再次同步不抹除。
7. 密碼只從環境變數讀（ADR-0006）。

## 取捨

| 考慮過的做法 | 為什麼沒有選 |
|---|---|
| `SELECT`＋`STORE` 同步已讀 | 改動伺服器狀態，違反唯讀原則 |
| 只支援單一 `INBOX` | 現況取捨；多 mailbox 排入 ROADMAP 第 5 項 |
| OAuth 流程 | 先用 App 專用密碼＋環境變數，避免引入複雜授權伺服器 |

## 後果

**正面**

- 供應商帳號零副作用，可放心重複同步、重設帳號設定。
- 憑證即使外洩，攻擊面也僅限讀取。

**負面／代價**

- 本機與遠端狀態會分歧，UI 必須以本機覆寫為準並說清楚。
- 無法使用伺服器端的資料夾操作；多資料夾要另做（ROADMAP 第 5 項）。

## 證據

- `README.md`「Real mail」段：「opened with EXAMINE and fetched with BODY.PEEK, so nothing on the server changes, not even the read flag」。
- `docs/fmb/ARCHITECTURE.md` 第 5.2 節特性第 3 點、第 7.2 節。
- `accounts.example.json` 與 README 的帳號設定範例。
