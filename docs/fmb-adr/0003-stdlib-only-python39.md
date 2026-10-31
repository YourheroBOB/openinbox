# ADR 0003：只用 Python 3.9 標準函式庫

- 狀態：已接受（回溯整理）
- 相關程式：`install.sh`（版本檢查）、`server/`（全部）、`CONTRIBUTING.md`、`.github/workflows/smoke.yml`

## 背景

目標使用者是「想在自己的機器上跑一個信箱腦」的人，不一定有 Python 開發環境。
`install.sh` 只檢查 `python3` 是否 ≥ 3.9，然後就結束了——沒有 virtualenv、沒有 `pip install`。
這個承諾一旦破功，安裝體驗與可審計性都會一起消失。

## 決策

`server/` 底下**不得引入任何第三方套件**，常見需求都自己寫：

| 需求 | 做法 |
|---|---|
| HTTP 伺服器與路由 | 標準庫的 handler + `server/features/` 的自註冊路由（ADR 0004） |
| 資料儲存 | `sqlite3`；全文搜尋用 FTS5，沒有 FTS5 就退回 `LIKE` |
| IMAP | `imaplib`（唯讀，見 ADR 0008） |
| 行事曆 | 自己寫的 ICS 解析／產生（`server/features/_ics.py`） |
| PWA 圖示 | `zlib` 自繪 PNG（`server/features/mobile.py`） |
| MCP | `json` + stdio 手寫 JSON-RPC 2.0（ADR 0010） |
| 測試 | `unittest`（`python3 -m unittest discover -s tests`） |

例外只有一種：**可選 adapter**，而且必須在沒有它時仍能運作（有 fallback），並且不得成為預設路徑。

## 取捨

**我們放棄**

- Web 框架（Flask／FastAPI）帶來的便利：路由裝飾器、請求解析、中介層都要自己維護。
- 成熟的套件：`icalendar`、影像處理、MCP SDK 都要自己實作最小可用版本。

**我們得到**

- clone 下來就能跑；CI 不用裝任何東西。
- 相依風險為零：沒有套件更新、沒有供應鏈攻擊面。
- 使用者可以逐行讀完伺服器在做什麼。

**已知代價**

- 自己寫的解析器（ICS、自然語言查詢、摘要啟發式）覆蓋率有限，需要靠測試與 fallback 補。
- 需要 FTS5 這類「SQLite 編譯選項」時，必須假設它可能不存在。

## 後果

- 新功能的預設實作必須是標準庫；如果要接外部服務，走 `agent.json` 的 BYO driver（ADR 0005），而不是新增 import。
- 依賴 SQLite 擴充功能時，一定要有降級路徑（搜尋已示範：回應帶 `engine` 欄位，讓使用者知道現在用哪一種）。
- 測試不得為了方便而引入測試框架；沿用 `unittest` 與既有的 `tests/_tpi_*.py` 輔助模組。
- 若真的必須新增第三方套件，先開 ADR：說明為何標準庫做不到、如何保持「沒有它也能跑」。
