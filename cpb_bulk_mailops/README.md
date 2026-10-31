# 資料夾批次多選（新增式交付）

## 做了什麼

補完 `state/tpi-mailops.md` 的 `next:`「資料夾批次多選操作」。閱讀兩版
README、STATE、各工作包後續註記與相關程式後選定此項：它直接改善日常整理信件，
而 `server/features/mailops.py` 的 `/api/mailops/action` 已支援多筆 ID，
因此不需修改後端、不需新增依賴，也不需另建資料表。

本次查閱時，倉庫沒有獨立 TODO／ROADMAP 檔案；規劃依據為 `STATE.md` 與
`state/*.md`。GitHub issue 唯讀查詢的 open／closed 清單皆為空，未推論額外需求。

`ui/modules/cpb_bulk_mailops.js` 由現有 `/api/ui-modules` loader 自動載入。
啟動原本 App 後，在信件資料夾會看到勾選框與「批次操作」列；不需任何程式整合 patch。

支援封存、移到垃圾桶、加／取消星號、已讀／未讀，以及移到收件匣、封存或垃圾桶。
全選有部分選取提示；勾選不會開信；鍵盤 Space 可切換勾選；按「套用」會先確認
動作與封數。處理中鎖住批次控件，避免重複送出。繁體中文／英文標籤隨 App 切換。

所有操作重用既有本機 API，只改本機 SQLite 狀態，不變更遠端信箱、不寄信。
選取 ID 僅存在頁面記憶體，不寫入 localStorage 或其他檔案；沒有遙測或內容紀錄。

## 保守邊界／決策點

- 全選**僅限當前已載入列表**（目前最多 120 封），不代表整個資料夾；不做跨頁或跨篩選保留。
- 列表重建、切換資料夾／帳號／分類／搜尋會清除選取。既有語言切換會重載列表，亦清除選取。
- 本機撰寫草稿不提供勾選；示範寄件備份可封存／移動／標星，但禁用已讀／未讀，避免既有虛擬資料來源無法反映這些變更。
- 不提供永久隱藏／清空垃圾桶的批次捷徑。每次套用都需人工確認，包含非破壞性動作。
- API 部分成功時顯示實際成功／找不到的封數與錯誤提示，然後刷新列表；不假裝全部成功。
- 網路、HTTP 或不完整回應會明確報錯，不自動重試。若連線中斷時後端可能已寫入，應先重新整理查核。

上述為本次工程選擇，非 BOB 既有拍板。請 BOB 決定是否保留逐次確認，
以及未來是否擴充跨頁選取或本機草稿批次處理；本次不先行放寬。

## 可執行測試

在倉庫根目錄執行：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s cpb_bulk_mailops -v
```

Python 測試只用標準函式庫，沿用 `tests/_tpi_server.py` 的拋棄式
`OPENINBOX_ROOT`、虛構信件與隨機 loopback 埠，不讀本機正式帳號或 Agent 設定。
測試結束由既有 harness 清除暫存資料與停止伺服器。

11 個 unittest 包含跨帳號批次狀態、部分／全部找不到、跨來源拒絕、
原信與草稿保留、同步後保留本機狀態、模組自動提供、雙語鍵值及 JS 語法。
Chrome＋Node.js 可用時，會實跑 `cpb_browser_test.js`：
120 封上限、勾選與 Space、確認取消、精確提交 ID、各種操作、重載清除、
草稿排除、示範寄件備份限制、部分成功、網路／HTTP／回應異常、
重複提交、請求中切換頁面，以及 390px 窄螢幕。
沒有 Chrome／Node.js 時相關項目會明確 skip，不視為瀏覽器驗收通過。

既有 `python3 -m unittest discover -s tests` 不會發現根目錄下這組測試；
請另外執行上述命令。本次未改 CI workflow。

### 本次實跑結果

- 新增組：11 個 unittest 全數通過，含 Chrome 42 項實際互動檢查，瀏覽器 runtime exception 為 0。
- 既有 mailops 與 repo guardrail 組：64 個測試，63 通過、1 跳過（既有 Chrome dump-dom 渲染測試逾時）。
- 測試期間既有 HTTP handler 在瀏覽器連線中止時曾輸出 `BrokenPipeError`；沒有造成上述新增測試失敗，本次未修改 handler。

## 新增檔案

| 檔案 | 用途 |
|---|---|
| `ui/modules/cpb_bulk_mailops.js` | 自動載入的批次多選介面 |
| `cpb_bulk_mailops/test_cpb_bulk_mailops.py` | 隔離 API 回歸、語法與 Chrome 測試入口 |
| `cpb_bulk_mailops/cpb_browser_test.js` | 本機 Chrome CDP 操作驗收 |
| `cpb_bulk_mailops/README.md` | 用法、邊界、測試與待決策事項 |

既有檔案均不修改；不 push、merge、改 remote、刪分支，亦不改 workflow 或憑證。

## 可選文件 patch（僅建議，未套用）

BOB 若要讓主 README 更容易發現此功能，可各加一行：

```diff
--- README.zh-Hant.md
+++ README.zh-Hant.md
@@
 ## 測試
+資料夾支援批次多選；用法與額外測試見 [批次操作](cpb_bulk_mailops/README.md)。
--- README.md
+++ README.md
@@
 ## Tests
+Folder multi-select: [usage and additional tests](cpb_bulk_mailops/README.md).
```

## English

This additive UI completes the folder multi-select follow-up in `state/tpi-mailops.md`.
The existing module loader enables it automatically; no integration patch is required.
It uses the existing local-only batch API, confirms every action, limits selection to displayed
messages, excludes local drafts, and reports partial failures explicitly. Run the command
above for isolated API checks and real Chrome CDP interactions. Existing files and CI are unchanged.
