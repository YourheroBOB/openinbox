# ADR-0007：只綁 127.0.0.1 與本機 Origin 檢查

- 狀態：已接受（現況仍有效）
- 日期：事後補建（原始決策日未記錄）
- 影響範圍：`server/app.py`、`server/features/_origin.py`、`run.sh`、文件
- 相關：ADR-0006、ADR-0015；ROADMAP 第 3 項

## 背景

系統沒有登入、沒有多使用者、沒有權限模型——因為它是單機單使用者工具。在這種前提下，
把 HTTP 服務綁到所有網卡等於把整個信箱暴露給區網；而瀏覽器端的跨來源 POST 需要一層
基本緩釋。

## 決策

1. HTTP 服務**只監聽 `127.0.0.1:8770`**（可用 `OPENINBOX_PORT` 換埠）。
2. 不提供 `0.0.0.0` 模式、不附反向代理設定、不寫任何部署腳本；遠端使用一律
   `ssh -N -L 8770:127.0.0.1:8770`。
3. 會改變資料（或實務上暴露本機資料）的端點，開頭呼叫 `_origin.local_origin(req)` 檢查，
   非本機來源以 `refuse(...)` 拒絕——`server/features/agents.py` 的每個 POST／GET 都是這個模式。
4. MCP 走 stdio，不開任何網路埠（ADR-0015）。

## 取捨

| 考慮過的做法 | 為什麼沒有選 |
|---|---|
| 內建帳密／多租戶 | 單機定位不需要，且引入 session 管理負擔 |
| 自架 TLS 與憑證 | SSH 通道已提供傳輸加密；自架憑證只增加失敗模式 |
| 不做 Origin 檢查 | 成本極低的 CSRF 緩釋，沒有理由省略 |

## 後果

**正面**

- 預設攻擊面最小：本機防火牆只需擋 8770。
- 遠端使用模式（SSH App、tmux）在文件有一致做法。

**負面／代價**

- 雲端共用、多人協作不在設計內；文件要不斷提醒「不要對外開放」。
- Origin 檢查是**緩釋不是認證**，不能當成唯一安全界線；真正的邊界是「只有本機行程與使用者能碰到 127.0.0.1」。

## 證據

- `README.md`「Run on a cloud Linux host」段。
- `docs/fmb/ARCHITECTURE.md` 第 2 節執行拓撲、第 8.1 節。
- `server/features/agents.py`：`if not local_origin(req): return refuse(req.lang_zh())`。
