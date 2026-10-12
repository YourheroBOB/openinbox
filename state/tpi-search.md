# tpi-search

goal: 自然語言搜尋：SQLite FTS5 索引＋中英文自然語言查詢解析（寄件人、日期區間、有附件、類別），可選 BYO agent 改寫查詢；聯絡人清單與搜尋 /api/contacts。對應 F11 F12。
status: done
next: （可選）在 server/mcp_server.py 加 search／contacts 工具；README 補一段搜尋語法（留給整合時做，避免與平行分支衝突）

## 交付

- `server/features/search.py`（F11）
  - FTS5 索引 `search_docs` + `search_fts`，中日文字切成重疊 bigram（unicode61 tokenizer，不依賴 trigram）；單一中文字自動退回 LIKE；本機 SQLite 沒有 FTS5 時整體退回 LIKE（`engine: "like"`）。
  - 索引在每次搜尋前依簽章增量更新；刪信由 trigger 同步刪索引列，所以清除本機快取（`/api/cache/clear`）也會清掉索引文字。
  - 查詢解析（中英文）：寄件人／收件人（會比對聯絡人）、日期區間（上週、最近3天、9月15日之後、9/14到9/15、last week、since Sep 15、between…and…、2 days ago…）、有／沒有附件、未讀／已讀、類別（需要你、電子報、important、newsletters…）、OR／或、`-排除字`、引號片語；也吃 Gmail 式運算子 `from: to: subject: after: before: on: newer_than: older_than: has: is: category: account:`。輸出 canonical 運算式與繁中／英文解讀 chip。
  - 相對日期錨點：`today=` 參數 > `OPENINBOX_TODAY` > demo 模式取最新一封信日期 > 系統時鐘（回應帶 `anchor_source`）。
  - BYO agent 改寫：`POST /api/search {"agent": true}` 或 `GET ?agent=1`，用 agent.json 的 driver（openai_compatible／cli／http）把句子改寫成一行運算式再搜尋；local 或失敗時退回內建解析並註明。
  - 路由：`GET/POST /api/search`、`GET /api/search/parse`、`GET /api/search/status`、`POST /api/search/reindex`。
- `server/features/contacts.py`（F12）：`GET /api/contacts?q=&sort=frequent|recent|name&people=1`、`GET /api/contacts/<email>`；由 From／To 彙整，排除自己的信箱，標記 noreply／電子報等自動寄件者。
- `ui/modules/search.js`：工具列搜尋框改走 `/api/search`，顯示解讀 chip、結果數、引擎、canonical、Agent 改寫開關、清除；空白聚焦時給範例；新增「聯絡人／Contacts」視圖（搜尋、排序、只看真人、詳情、一鍵搜尋此人的信）；支援 `#q=` 與 `#view=contacts`。繁中／英文字串齊全。
- 未改 `server/app.py`、`ui/index.html`（全走既有外掛與 UI 模組載入器）。
- 測試：`tests/test_tpi_search_parse.py`、`_index.py`、`_agent.py`、`_contacts.py`、`_ui.py`（共 52 個）。示範資料只用 fixtures 與 example.com 虛構信件。

## log

- 2026-10-11 16:40 +0800 實作 search.py（FTS5＋中英文解析＋agent 改寫）、contacts.py、ui/modules/search.js 與 5 個測試檔；驗證：`python3 -m unittest discover -s tests` 198 tests OK、`scripts/smoke.sh` OK、暫時伺服器以 headless Chrome 載入 `#q=from:samira has:attachment` 與 `#view=contacts` 確認 UI 實際渲染結果與聯絡人清單。
