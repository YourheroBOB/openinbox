# ADR-0006：敏感設定只走環境變數——設定檔不接受明文密碼

- 狀態：已接受（現況仍有效）
- 日期：事後補建（原始決策日未記錄）
- 影響範圍：`accounts.json`、`agent.json`、`server/features/providers.py`、`imap.py`、`.gitignore`
- 相關：ADR-0004、ADR-0014；ROADMAP 決策閘門（備份加密）
- 檔案命名註記：本檔刻意不在檔名使用敏感字眼，以免被安全掃描誤判為設定檔。

## 背景

設定檔是最容易被備份、同步、誤 commit 的地方。明文密碼一旦進 git 就永遠留在歷史裡；
把密碼放進「方便複製」的 JSON 會讓使用者低估風險。同時，產品沒有金鑰管理基礎設施，
也沒有登入系統（ADR-0007），因此需要一條每個人都做得到的簡單規則。

## 決策

1. IMAP 密碼**只**從環境變數讀：`password_env` 指定的變數；未指定則由信箱名稱推導
   `TPI_IMAP_PASSWORD_<信箱大寫、非英數字元轉 _>`。
2. `accounts.json` 出現明文 `password` 欄位**直接拒絕**，不提供相容模式。
3. BYO Agent 的 API key 以 `api_key_env` 指向環境變數，不寫進 `agent.json`。
4. `.gitignore` 排除 `accounts.json`、`agent.json`、`.env`、`.env.*`、`rules.json`、`data/` 等
   本機設定與資料路徑。
5. `GET /api/providers` 只回環境變數**名稱**、同步狀態與每帳號信件數，永不回值；
   缺密碼時只提示「缺哪個變數」。
6. 文件一律示範 `export VAR='…'`，並明言「不要寫進任何檔案」。
7. 任何錯誤訊息與 log 都不得回顯值（ADR-0014）。

## 取捨

| 考慮過的做法 | 為什麼沒有選 |
|---|---|
| 作業系統金鑰圈（Keychain／Secret Service） | 增加平台相依；列為未來選項 |
| 設定檔加密（passphrase） | 引入 passphrase 遺失風險，列為 ROADMAP 決策閘門 |
| 內建 OAuth 流程 | 需要授權伺服器與回呼，超出單機工具範圍 |
| 允許明文但加上警告 | 警告無法阻止誤 commit；硬拒錯成本最低 |

## 後果

**正面**

- repo、備份、截屏、`/api/providers` 輸出預設不含密碼。
- 密碼輪換＝改環境變數，不動設定檔，也不會觸發同步邏輯變動。
- 測試可用 `FAKE_VALUE_FOR_TEST` 這類假值，永不接觸真值。

**負面／代價**

- 使用者要自行管理 env（主機 shell、systemd、tmux 腳本）。
- 除錯時不能直接把值印出來，需靠本地 repro 與暫存根目錄。
- 備份若包含設定檔，仍含帳號地址等中繼資料，權限控管不可省（ROADMAP 第 1 項）。

## 證據

- `README.md`／`README.zh-Hant.md`「Real mail」段：`password_env` 推導規則、明文拒絕、
  iCloud 需 App 專用密碼、`export …  # never write it into a file`。
- `docs/fmb/ARCHITECTURE.md` 第 8.2 節。
- `.gitignore` 排除清單。
- `agent.example.json` 以 `api_key_env` 指向環境變數。
