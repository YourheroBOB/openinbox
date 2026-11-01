# openinbox 相依套件升級計畫

本目錄為「語言版本、相依套件與執行環境盤點＋分階段升級計畫」文件，**只新增 Markdown，不修改產品碼、測試、CI、secrets、git 設定，也未實際升級任何元件**。

## 1. 目的

openinbox 的核心定位是單機、本機優先、零 pip 的 Python 應用。升級重點不是引入大量第三方套件，而是：

1. 更新語言版本政策與執行環境支援矩陣。
2. 找出 Python 3.9+ 政策中已過時或接近生命週期結束的版本。
3. 管理 SQLite／FTS5、PWA／瀏覽器、MCP 協定與可選外部驅動的相容性。
4. 提供可回滚、可驗證、不影響本機資料的分階段計畫。

## 2. 範圍

| 層面 | 包含項目 |
|---|---|
| 語言版本 | Python、Bash、Node.js（僅開發檢查）、瀏覽器／PWA 執行期 |
| 內建相依 | Python 標準函式庫、`sqlite3`、FTS5／LIKE 搜尋、JSON／HTML／PWA 資產 |
| 協定 | MCP over stdio、JSON-RPC 2.0、HTTP API 內部契約 |
| 可選外部相依 | IMAP 供應商、`gog`／`gsk` CLI、OpenAI 相容端點、CLI／HTTP Agent、ICS feed |
| 執行環境 | 本機單行程、`127.0.0.1:8770`、demo／live 模式、Unix shell |

明確不包含：

- 不引入託管模型或遙測。
- 不新增預設寄信路徑。
- 不自動升級外部正式服務。
- 不修改 `.github/workflows`、secrets、憑證、git remote。
- 不執行 git push／merge。

## 3. 文件索引

| 檔案 | 內容 |
|---|---|
| `docs/fmb-upgrade/README.md` | 本檔：目的、範圍、共同原則、決策閘門 |
| `docs/fmb-upgrade/inventory.md` | 語言版本、相依套件、執行環境盤點與風險評估 |
| `docs/fmb-upgrade/phased-plan.md` | 分階段升級計畫：每步變更、相容性風險、驗證、回滾 |
| `docs/fmb-upgrade/validation-and-rollback.md` | 驗證矩陣、本機安全測試指令、回滾演練 |
| `docs/fmb-upgrade/risk-register.md` | 風險登錄表與決策點 |

## 4. 共同原則

1. **保守升級**：先盤點與驗證，再改政策；不因文件撰寫而實際升級。
2. **零 pip 不被破壞**：除非未來獨立決策，伺服器核心仍維持 Python 標準函式庫。
3. **向後相容優先**：新協定欄位、新工具、新 UI 快取不得讓舊客戶端或舊快取直接失敗。
4. **本機資料安全**：任何涉及 SQLite／FTS5／衍生資料的階段，必須先備份並支援 dry-run。
5. **測試隔離**：使用 `tmp_path`／`tempfile`，外部相依一律以本地 fake 取代。
6. **敏感資料零落地**：不寫入 token、金鑰、密碼、客戶個資、LINE 訊息內文或案件當事人資料；測試假值只用 `FAKE_VALUE_FOR_TEST`。
7. **不連正式服務**：驗證只跑本機 unittest、smoke、本機 loopback fake；不呼叫正式 IMAP、Agent、ICS、MCP 正式服務。

## 5. 安全與測試規範

1. 測試與驗證指令不得讀寫 repo 以外的正式使用者資料；必要時使用暫存根目錄。
2. 需要假端點、假金鑰、假密碼時，只用 `FAKE_VALUE_FOR_TEST` 這類明顯假字串。
3. 不使用 `sk-`、`ghp_`、`xox` 等任何真實格式前綴。
4. 錯誤訊息、日誌、manifest 不得包含郵件內文、寄件人、案件資料、憑證或外部端點原始回應。
5. 任何階段若需要改動 `.github/workflows`，都必須先經 BOB 決策；本文件不授權現在修改。

## 6. 決策閘門

| 決策 | 保守預設 | 需 BOB 確認 |
|---|---|---|
| Python 最低版本 | 由 3.9 升至 3.11，測試 3.11–3.13 | 是否支援 3.14、是否保留 3.10 過渡期 |
| Node.js 定位 | 僅開發期檢查，不是產品執行期相依 | 是否列入必要 CI |
| 瀏覽器支援下限 | 只支援具備 optional chaining／nullish coalescing 的現代瀏覽器 | 是否為舊 Safari 保留轉譯流程 |
| SQLite／FTS5 | 自動偵測，FTS5 缺少時維持 LIKE fallback | 是否將 FTS5 列為必要 |
| MCP 協定 | 維持現有工具相容，新增能力需可安全忽略 | 是否加入行事曆等新唯讀工具 |
| 可選外部 CLI | 不自動升級，只建立版本契約與 fake 測試 | 是否接受最低版本範圍 |
