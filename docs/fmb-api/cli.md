# CLI 指令參考

## 1. `./install.sh`

- 檢查 `python3` 存在且版本 ≥ 3.9，否則結束。
- 建立 `data/`、`vault/cards/`。
- 缺少時複製 `accounts.example.json` → `accounts.json`、`agent.example.json` → `agent.json`；已存在則不覆寫。
- 印出啟動說明（示範模式預設，不必登信箱）。

## 2. `./run.sh`

- 沒有 `accounts.json` 會先呼叫 `./install.sh`。
- 設定 `OPENINBOX_ROOT` 為 repo 根目錄。
- 設定 `OPENINBOX_PORT`，未設定時預設 `8770`。
- 前景執行 `python3 server/app.py`。

常用環境：`OPENINBOX_NO_BROWSER=1 ./run.sh`（雲端主機、tmux／screen 常駐）。

## 3. 測試

```bash
python3 -m unittest discover -s tests   # 標準函式庫 unittest，使用拋棄式資料夾
scripts/smoke.sh                        # CI smoke 檢查（Linux 本機）
```

測試慣例：只用 `tempfile`／暫存根目錄與虛構資料，不連正式服務；假憑證用明顯假字串（例如 `FAKE_VALUE_FOR_TEST`）。

## 4. MCP 伺服器

```bash
python3 server/mcp_server.py            # stdio MCP；不需要先跑網頁面板
```

協定與工具見 [mcp-api.md](mcp-api.md)。

## 5. 其他腳本

| 腳本 | 狀態 |
|---|---|
| `scripts/overnight.py` | 存在於儲存庫；用途與參數待確認（名字對應夜班分流流程） |
| `scripts/smoke.sh` | 本機 smoke 檢查（見上） |

## 6. `fmb_feature2/`（獨立模組，未接線）

自包含的附加模組：RFC 3501 modified UTF-7 mailbox 名稱、唯讀 LIST 解析、以及針對 `accounts.json` 內 IMAP 項目的離線預檢。不 import 應用程式；要啟用時把模組複製到 `server/features/`（見其 `README`）。對應測試：`tests/test_fmb_contract_feature_imap_mailbox.py`、`tests/test_fmb_integration_fmb_feature2_standalone.py`。
