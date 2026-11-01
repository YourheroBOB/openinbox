# openinbox 架構決策紀錄（ADR）

本目錄收錄 openinbox「已經在做、但過去沒有明文寫下」的重要架構決策，逐篇整理成
ADR（Architecture Decision Record）。每篇固定四節：**背景、決策、取捨、後果**，
並附「證據」欄指明這項決策在 repo 內的依據，方便日後用 `grep` 複查。

## 這份文件的分工

| 文件 | 回答的問題 |
|---|---|
| `docs/fmb/ARCHITECTURE.md` | 現在**長什麼樣子**（模組、資料流、API） |
| `docs/fmb/ROADMAP.md` | 未來**要做什麼**（待辦、決策閘門） |
| `docs/fmb-adr/`（本目錄） | 當年**為什麼這樣設計**、放棄了什麼 |
| `docs/fmb-adr/ONBOARDING.md` | 新進開發者**怎麼上手**（模組地圖、修改路徑、陷阱） |

## 事後補建聲明（重要）

這批 ADR 是依任務提供的 repo 快照**回溯整理**，不是從當年的決策會議紀錄轉錄。
因此：

- 每篇的「日期」欄標為**事後補建**，不假造原始決策日。
- 「證據」欄只引用快照中可讀到的檔案（README、ARCHITECTURE、CONTRIBUTING、
  adapters 說明、`server/features/agents.py`、`ui/modules/agents.js`、設定範例等）。
- 快照中**未提供原始碼**的模組（如 `server/app.py`、`server/yhbmail.py`、
  `server/agent_bridge.py`、`server/mcp_server.py`、`search.py`、`outbox.py`），
  相關敘述以文件與可讀程式碼為據，實施前請自行確認。

## 狀態定義

| 狀態 | 意義 |
|---|---|
| 已接受 | 現況仍有效，新碼應遵守 |
| 已取代 | 被更新的 ADR 取代，保留供追溯 |
| 待決 | 還沒定案（本目錄目前沒有此類；待決項集中在 ROADMAP 決策閘門） |

## 索引

| 編號 | 標題 | 一句話決策 |
|---|---|---|
| [ADR-0001](adr-0001-local-first-single-process.md) | 本機優先：單行程、標準庫、零 pip | 一個 Python 行程、只用標準庫，換取可攜、可審查、零安裝 |
| [ADR-0002](adr-0002-modular-monolith-auto-registration.md) | 模組化單體與外掛自動註冊 | 檔案丟進 `features/`、`ui/modules/` 即擴充，核心不動 |
| [ADR-0003](adr-0003-no-default-send-human-confirmed-outbox.md) | 不預設寄信：人工確認的 outbox | 草稿→明確確認→本機 outbox，沒有任何路徑能繞過人 |
| [ADR-0004](adr-0004-read-only-imap.md) | 唯讀 IMAP | `EXAMINE` + `BODY.PEEK`，伺服器上零改動 |
| [ADR-0005](adr-0005-byo-agent-drivers-local-fallback.md) | BYO Agent 四驅動與本機後備 | 本機先算、Agent 改寫、失敗誠實標 fallback；郵件文字一律視為資料 |
| [ADR-0006](adr-0006-environment-only-config.md) | 敏感設定只走環境變數 | 設定檔不接受明文密碼，API 只回變數名稱 |
| [ADR-0007](adr-0007-loopback-bind-and-origin-check.md) | 只綁 127.0.0.1 與本機 Origin 檢查 | 預設攻擊面最小，遠端使用靠 SSH 通道 |
| [ADR-0008](adr-0008-single-sqlite-and-local-files.md) | 單一 SQLite + 本機檔案，FTS5 退 LIKE | 一庫多表加檔案衍生資料，搜尋能力依 SQLite 編譯降級 |
| [ADR-0009](adr-0009-bilingual-ui-contract.md) | 雙語 UI 契約 | 每個介面字串 zh／en 成對，禁止簡體 |
| [ADR-0010](adr-0010-pwa-never-caches-api.md) | PWA 不快取 `/api/*` | 離線只剩殼，郵件內容不進瀏覽器儲存 |
| [ADR-0011](adr-0011-deliverable-id-escape-sandbox.md) | 成果安全：ID 正則、全轉義、sandbox | 路徑穿越與 XSS 的雙層防線 |
| [ADR-0012](adr-0012-plugins-are-trusted-code.md) | 外掛是受信任本機程式碼 | 不宣稱沙箱，治理靠明確的信任邊界 |
| [ADR-0013](adr-0013-demo-mode-default.md) | 示範模式為預設 | 開箱即可用，live 模式是選配 |
| [ADR-0014](adr-0014-error-and-log-hygiene.md) | 錯誤與日誌淨化 | 對外只回例外類型與 HTTP 狀態，不吐內容 |
| [ADR-0015](adr-0015-mcp-stdio-single-write.md) | MCP：獨立 stdio 程序、單一寫入 | 不需面板即可用；`save_draft` 是唯一可寫工具 |

## 怎麼新增一篇 ADR

1. 編號遞增，檔名 `adr-NNNN-kebab-case.md`，內容用繁體中文。
2. 沿用四節結構：背景、決策、取捨（可用表格列「考慮過的做法／為何不選」）、後果（正面／負面）。
3. 補「證據」欄：引用 repo 內實際存在的檔名或行為；推斷處明確標注。
4. 檔名避免使用 `credential`、`secret`、`token`、`key` 這類字眼，以免被安全掃描誤判為
   設定檔而拒收；需要描述這類主題時，用「環境變數」「敏感設定」等中性詞。
5. **不修改已發表的 ADR**；決策改變時寫新的一篇，並在舊篇標「已取代」。
6. 理想流程：先有 ADR，再有實作碼；修 bug 不須新 ADR，改變方向才須。
