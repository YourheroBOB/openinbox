# fmb ADR 索引：openinbox（TooPowerInbox）架構決策紀錄

這批文件把 openinbox 目前**已經在程式碼裡成立**的設計決策，回溯整理成架構決策紀錄（retrospective ADR），
外加一份新進開發者上手指南。目的只有一個：讓下一個改這個 repo 的人，在動手前就知道「哪些線不要踩、為什麼」。

- 上手指南：[`onboarding.md`](onboarding.md)
- 這批文件只描述現狀與其理由，**不提案新功能**，也**不代表任何商業產品的實作**。
- 文件內容以繁體中文撰寫，程式識別字（路徑、函式、參數、driver 名稱）保留英文原文，方便 grep。

## 撰寫原則

1. 只寫能從程式碼、README、`state/*.md` 與測試觀察到的行為；不臆造未實作的選項。
2. 決策若在程式碼中已有多處落實（例如每個寫入端點都做 Origin 檢查），就寫成「已接受的慣例」，而不是「建議」。
3. 範例資料一律使用虛構值（`example.com`、`you@example.com`、`FAKE_VALUE_FOR_TEST`），不引用任何真實信件、人名或憑證。
4. 涉及寄送、憑證、隱私的段落，只描述邊界與做法，不描述如何繞過。

## 清單

| 編號 | 標題 | 一句話 |
|---|---|---|
| [0001](0001-single-process-local-first.md) | 單一行程、本機優先、只聽 loopback | 一個 python3 行程同時是 API 與面板，唯一的入口是本機埠（或 SSH 通道） |
| [0002](0002-no-send-path.md) | 不提供寄送路徑 | 所有輸出停在草稿／outbox／成果卡片，寄送永遠由使用者自己做 |
| [0003](0003-stdlib-only-python39.md) | 只用 Python 3.9 標準函式庫 | clone 下來就能跑，代價是很多東西要自己寫 |
| [0004](0004-plugin-features-and-ui-modules.md) | 外掛式 features 路由與自動載入 UI 模組 | 新功能只新增檔案，不改 `app.py`／`index.html` |
| [0005](0005-byo-agent-bridge.md) | BYO agent bridge，`local` 是萬年後備 | 不附託管模型；沒有 agent 也要能用，且要明確標示 |
| [0006](0006-local-cache-and-clear.md) | 本機快取與「可清除」契約 | 快取可一鍵清掉，使用者資產必須留著 |
| [0007](0007-vault-persona-and-second-brain.md) | vault：persona 與 Second Brain 的檔案式記憶 | 記憶是可讀、可備份的檔案，且不進 git |
| [0008](0008-read-only-connectors.md) | 唯讀連接器與憑證只從環境變數 | 接了真信箱也不會改動伺服器上的任何狀態 |
| [0009](0009-loopback-origin-guard.md) | 寫入端點的本機 Origin 防護 | 瀏覽器裡的其他網站不能叫動這台機器 |
| [0010](0010-mcp-stdio-server.md) | MCP stdio 伺服器重用既有工具層 | 同一組工具同時給 HTTP `/api/v1` 與 MCP 客戶端 |
| [0011](0011-file-based-deliverables.md) | 成果卡片存檔案 | agent 產出是可匯出的 MD／HTML 檔，id 嚴格驗證 |
| [0012](0012-pwa-static-only-service-worker.md) | PWA service worker 只快取靜態資源 | 可以安裝成 App，但瀏覽器裡不留任何信件 |
| [0013](0013-bilingual-zh-hant-first.md) | 雙語（繁中優先）與字串規則 | 每個使用者可見字串都要有 `zh` 與 `en` |
| [0014](0014-demo-mode-and-fictional-fixtures.md) | 示範模式與虛構 fixtures 為預設 | 預設 `demo`，repo 內不得出現真信箱 |

## 狀態術語

- **已接受（Accepted）**：程式碼已如此運作，新程式碼必須維持。
- **回溯整理**：不是當初開會決定的，而是從現有實作歸納出來的；若之後要改，屬於破壞性變更，需要新的 ADR 說明理由與影響。
- **例外**：少數核心檔案（`server/app.py`、`ui/index.html`）仍可能有「最小掛勾」式改動，見 ADR 0004。

## 什麼時候要新增 ADR

只要符合下列任一項，就在 `docs/fmb-adr/` 新增一篇（編號遞增，不改舊文）：

- 會讓資料離開這台機器（任何形式的寄送、上傳、第三方同步）。
- 會改變資料保存邊界（新資料表、新檔案、清快取的行為）。
- 會引入 pip 套件、背景服務、對外连接埠或反向代理。
- 會改變 agent 的信任邊界（把郵件內容當指令、把使用者資料塞進 prompt、把原始錯誤訊息回給使用者）。
