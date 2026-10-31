# ADR 0014：示範模式與虛構 fixtures 為預設

- 狀態：已接受（回溯整理）
- 相關程式：`accounts.example.json`、`agent.example.json`、`fixtures/*.json`、`fixtures/ics/*.ics`、`install.sh`（首次複製設定檔）、`server/yhbmail.py`（demo 種子）、`tests/test_tpi_foundation_repo_rules.py`

## 背景

這個 repo 是公開的，而它的資料模型就是「信件」。
只要有人不小心把真實信件、真實位址或真實人名放進 fixture、測試、截圖或文件，就會造成不可逆的外洩。
同時，新開發者要能 clone 下來就跑，不能要求他先接一個真信箱。

## 決策

1. **預設 `mode: demo`**：第一次啟動從 `fixtures/` 種入示範信件、寄件備份、回覆、行事曆與規則，面板立刻有東西看。
2. 所有示範資料**虛構**：位址一律 `example.com` 或其子網域、人名虛構、內容自造；示範郵件 id 有 `demo:` 前綴，方便辨識與清理。
3. 設定檔以 `.example.json` 形式進版控；真正的 `accounts.json`／`agent.json` 由 `install.sh` 複製產生並 gitignored。
4. 切到 `live` 模式要使用者自己改設定，憑證從環境變數來（ADR 0008）。
5. demo 模式下有些行為刻意不同（例如相對日期的錨點會取最新一封信的日期，讓示範資料永遠「新鮮」），回應會帶出錨點來源。
6. repo 內有規則測試守著（禁止真信箱樣式、禁止託管模型與遙測、禁止特定部署設定等）。

## 取捨

**我們放棄**

- 「用真實資料除錯最快」的便利；除錯請自己在本機建暫存資料。
- demo 與 live 行為完全一致（時區、日期錨點、同步來源都不同）。

**我們得到**

- 零隱私風險的 repo 與 CI；貢獻者不用交出任何信箱。
- 可重現的測試與截圖。

**已知代價**

- 示範資料的維護成本（改功能時可能要補 fixture）。
- 某些 bug 只在 live 才看得到，需要假伺服器（`tests/_tpi_imap_fake.py`）補足。

## 後果

- 新增測試資料：放 `fixtures/` 或測試自己造；**不得**貼真實信件片段、真實公司名、真實職稱組合。
- PR／issue／截圖／文件一律不得包含真實位址或可識別個人的內容；需要示意時用 `you@example.com` 這類佔位。
- 需要假憑證時用明顯的假字串（例如 `FAKE_VALUE_FOR_TEST`），不要用任何看起來像真金鑰的格式。
