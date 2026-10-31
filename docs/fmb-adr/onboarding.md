# 新進開發者上手指南（openinbox / TooPowerInbox）

這份指南假設你已經 clone 了 repo、切到自己的分支，而且**沒讀過任何程式碼**。
目標是讓你在半天內能安全地改一個小功能，並且知道哪些線不能踩。
先讀：[`README.md`](../README.md)（或 [`README.zh-Hant.md`](../README.zh-Hant.md)）、[`CONTRIBUTING.md`](../CONTRIBUTING.md)、本目錄的 [ADR 索引](README.md)。

---

## 1. 三十分鐘上手

```bash
./install.sh                 # 檢查 python3 >= 3.9，建 data/ 與 vault/cards，複製 *.example.json
OPENINBOX_NO_BROWSER=1 ./run.sh   # 只聽 127.0.0.1:8770
```

- 打開 `http://127.0.0.1:8770/`，左側可切 繁中／EN，或用 `?lang=zh-Hant`。
- 第一次開機會載入示範信（`fixtures/`）；你看到的一切都是虛構資料。
- 常用健康檢查：`curl -s http://127.0.0.1:8770/api/health`、`GET /api/features`（載入了哪些外掛與路由）。

跑測試（不需要網路、不需要 pip）：

```bash
python3 -m unittest discover -s tests
scripts/smoke.sh
```

`scripts/smoke.sh` 會直接解析 `.github/workflows/smoke.yml` 的步驟，在拋棄式副本上跑同一套檢查（含自動換埠）。
**不要修改** `.github/workflows/`。

---

## 2. 模組地圖

### 2.1 後端核心（`server/`）

| 檔案 | 角色 | 你會在這裡做什麼 |
|---|---|---|
| `app.py` | HTTP 入口、面板與核心 API；把 `features` 掛上去 | 幾乎不該改（見 ADR 0004） |
| `yhbmail.py` | 信箱脊：設定載入、driver 派送（`DRIVERS`／`LAST_SYNC`）、SQLite、分類、看板、信件與事件讀取 | 新增 driver、改 schema、改分類時進來 |
| `persona.py` | 「更了解你」：`vault/persona.json` → `vault/persona.md` | 改人格推論時 |
| `second_brain.py` | 卡片：`vault/cards/*.md`、`vault/index.json`、`search`、`add_card` | 改卡片格式或蒸餾規則時 |
| `agent_bridge.py` | BYO agent：`load_agent_cfg`、`context_pack`、各 driver、`TOOLS`／`invoke_tool` | 新增 agent 工具、改 prompt 組裝時 |
| `mcp_server.py` | stdio MCP 伺服器（重用上面的工具層） | 只在工具層變動時跟著確認 |

### 2.2 外掛功能（`server/features/`）

| 檔案 | 大致負責 | 對應能力 |
|---|---|---|
| `__init__.py` | 路由註冊（`get`／`post`／`Raw`／`mount`）與請求物件 | 所有外掛的基礎 |
| `plugins.py` | `/api/features`、`/api/ui-modules`、`/ui/modules/*` | 外掛與 UI 載入 |
| `_origin.py` | `local_origin`／`refuse` | 寫入端點防護（ADR 0009） |
| `cache.py` | `GET /api/cache`、`POST /api/cache/clear` | 快取契約（ADR 0006） |
| `imap.py` | 唯讀 IMAP driver（EXAMINE／BODY.PEEK） | 真信箱（ADR 0008） |
| `providers.py` | 帳號清單、每帳號計數、連線測試 | 多帳號統一收件匣 |
| `triage.py` | 四類分流、摘要、建議動作、digest、任務 | Super Agent 視圖 |
| `compose.py` | 撰寫／AI 起草／語氣與字型設定 | 草稿產生（永不寄出） |
| `outbox.py`、`_outbox_transport.py` | 排程、倒數、本機 outbox | Schedule／Undo（本機邊界） |
| `mailops.py` | 資料夾、標星、封存、刪除、全部已讀、列印、翻譯、帳號設定、簽名 | 信件操作與本機狀態覆蓋 |
| `search.py` | FTS5 + 自然語言查詢解析（含 `LIKE` 降級） | 找信 |
| `contacts.py` | 聯絡人彙整 | 聯絡人清單 |
| `email_brain.py` | 信件大腦五區與「修正」 | 讓推論可被使用者改寫 |
| `calendar.py`、`_ics.py` | 本機事件、ICS 匯入／產生、free/busy | 行事曆 |
| `followup.py` | 未回覆追蹤、自動化規則、夜班結果 | 追蹤與批次 |
| `rules.py` | JSON 規則 dry-run／套用 | 自動化 |
| `agents.py` | 代理協作：研究、會議準備、`@agent` 提及、成果卡片 | 見 ADR 0011 |
| `skills.py` | 技能清單、開關、執行 | `skills/*.md` |
| `usage.py` | BYOK 用量紀錄 | 用量頁 |
| `mobile.py` | manifest、`/sw.js`、離線頁、圖示、`/api/mobile/info` | PWA（ADR 0012） |
| `overnight.py` | 夜班批次的伺服器端部分（搭配 `scripts/overnight.py`） | 批次工作 |

> 這裡只寫「大致負責」。實際路由請以 `GET /api/features` 的輸出為準——那是唯一不會過期的清單。

### 2.3 前端（`ui/`）

| 路徑 | 角色 |
|---|---|
| `ui/index.html` | 面板外殼：三欄版面、鍵盤操作、核心 i18n、模組 loader、最小 PWA 掛勾 |
| `ui/modules/<name>.js` | 每個功能一支，自動載入；掛側欄按鈕、接管 `#pane` 的某個 `state.view` |
| `ui/pwa/sw.js`、`ui/pwa/offline.html` | service worker 與離線頁（由 `features/mobile.py` 提供） |

既有模組：`triage`、`compose`、`skills`、`search`、`email_brain`、`calendar`、`mailops`、`outbox`、`followup`、`agents`、`providers`、`cache`、`usage`、`mobile`。

### 2.4 其他

| 路徑 | 角色 |
|---|---|
| `skills/*.md` | 技能提示詞（繁中在前、英文在後） |
| `tests/` | `unittest` 測試；`_tpi_*.py` 是共用輔助（暫存伺服器、假 IMAP、假 agent、CDP 腳本） |
| `fixtures/` | 虛構示範資料（信件、寄件備份、回覆、行事曆、ICS、規則） |
| `scripts/smoke.sh`、`scripts/overnight.py` | 本機 smoke、夜班批次 |
| `install.sh`、`run.sh` | 安裝與啟動 |
| `state/` | 各 work package 的狀態與決策紀錄（歷史脈絡，不是規格書） |
| `vault/` | 人格與卡片（gitignored，見 ADR 0007） |
| `data/` | 快取與產出（gitignored） |

---

## 3. 資料流

### 3.1 同步（進）

```
accounts.json + 環境變數
        │
        ▼
yhbmail.sync_all ──► DRIVERS[driver]（demo / CLI 型 / imap …）
        │                     │
        │                     └─ 唯讀取信（EXAMINE + BODY.PEEK）
        ▼
本機 SQLite（信件、帳號標記、分類結果）＋ LAST_SYNC（每帳號結果）
        │
        ▼
features/providers.py ──► GET /api/providers ──► 側欄帳號清單
```

### 3.2 讀取（出）

```
ui/modules/*.js ──► GET /api/inbox | /api/triage | /api/search …
                          │
                          ▼
              features/*.py ──► yhbmail（SQLite）／second_brain（files）
                          │
                          ▼
                    JSON（含 lang 對應字串）
```

### 3.3 agent（BYO）

```
UI ──► POST /api/...（feature）
             │  1. 先算本機結果（啟發式）
             │  2. 組 context pack：persona + 相關信件片段 + rules + lang
             ▼
      agent_bridge.load_agent_cfg() ──► local / openai_compatible / cli / http
             │
             ▼
        文字結果 ──► 存檔（deliverable／執行紀錄／草稿）
             │
             ▼
  回應附 { driver, fallback, error } ──► UI 明確標示「本機啟發式」或「已退回本機」
```

### 3.4 輸出（永遠不離開本機）

```
compose ──► drafts（本機 SQLite）──► outbox（排程／倒數）──► 使用者自己帶走
mailops/print ──► HTML（使用者用瀏覽器存 PDF）
agents ──► data/deliverables/<id>.{md,html,json}
skills ──► data/slides/*.html
```

### 3.5 MCP

```
MCP 客戶端（stdio）──► mcp_server.py ──► agent_bridge.invoke_tool ──► yhbmail／second_brain
                        （不經 HTTP、不連網；save_draft 只寫本機且回 sent:false）
```

### 3.6 PWA

```
瀏覽器 ──► /manifest.webmanifest、/sw.js、/offline.html、圖示（features/mobile.py）
   sw 只快取：離線頁、manifest、圖示、ui/modules/*.js
   /api/*、POST、跨來源：不攔截、不快取
```

---

## 4. 資料與狀態放哪裡

| 位置 | 內容 | 進 git？ | 清快取時 |
|---|---|---|---|
| `accounts.json`、`agent.json`、`rules.json` | 使用者設定 | 否（由 `*.example.json` 複製） | 不動 |
| `data/` 的 SQLite | 信件快取、分類、執行紀錄、草稿、本機狀態覆蓋、修正 | 否 | 依 ADR 0006：快取清掉，草稿／修正／任務等保留 |
| `data/deliverables/`、`data/slides/` | agent 與技能的產出 | 否 | 屬產出物，行為以 `cache.py` 為準 |
| `data/contacts.json`、`data/skills.json`、`data/usage.jsonl` | CRM、技能開關、用量 | 否 | 保留（使用者資料） |
| `vault/persona.json`、`persona.md` | 人格 | 否 | 重建 |
| `vault/cards/*.md`、`vault/index.json` | 卡片 | 否（僅 `.gitkeep`） | 衍生卡片會重建；你自己寫的筆記要留 |
| `fixtures/` | 虛構示範資料 | 是 | reseed 時重新載入 |

**規則**：只要是真實個人資料，就不會進 git；只要會進 git，就必須是虛構的。

---

## 5. 常見修改路徑

| 我要… | 動這些檔案 | 注意 |
|---|---|---|
| 新增一個 API 功能 | `server/features/<name>.py` ＋ `tests/test_tpi_<name>.py` | 不要改 `app.py`；寫入端點第一行 `local_origin` |
| 新增一個面板畫面 | `ui/modules/<name>.js` | 自帶 `zh`／`en`；`state.view` 守衛；找不到節點就 return |
| 新增一個 agent 工具 | `agent_bridge.TOOLS` ＋ `invoke_tool` | HTTP `/api/v1` 與 MCP 同時生效；必須符合「不離開本機」 |
| 新增一個技能 | `skills/<name>.md`（繁中在前、英文在後） | 技能開關在 `features/skills.py`；關閉要拒跑；結果先本機算 |
| 新增一個郵件 driver | `yhbmail.DRIVERS` ＋ 一個 driver 模組 | 唯讀、憑證只從環境變數、錯誤訊息遮罩、附假伺服器測試 |
| 改分流／桶子 | `yhbmail.py` 分類 ＋ `features/triage.py` 映射 | 會連動 persona 優先序與 Second Brain 卡片，改完跑整包測試 |
| 新增持久化資料 | `yhbmail.py` schema ＋ `features/cache.py` ＋ 測試 | 先決定「快取」還是「使用者資產」（ADR 0006） |
| 改 AI 起草 | `features/compose.py` ＋ `agent_bridge.context_pack` | 先本機再 agent；fallback 要標示；不要外露原始錯誤 |
| 改行事曆 | `features/calendar.py`、`features/_ics.py`、`ui/modules/calendar.js` | 時區、`allow_private`、私密事件不露標題、大小上限 |
| 改搜尋 | `features/search.py` | FTS5 不存在時要退回 `LIKE`；相對日期要有錨點來源 |
| 改 PWA | `features/mobile.py`、`ui/pwa/sw.js`、`ui/modules/mobile.js` | 只快取靜態；改 manifest／圖示會影響快取版本 |
| 改核心 UI 外殼 | `ui/index.html` | 最後手段；只加最小掛勾，PR 說明原因 |

---

## 6. 測試與驗證

| 方式 | 指令 | 用途 |
|---|---|---|
| 單元／整合 | `python3 -m unittest discover -s tests` | 全部；測試自建暫存根目錄，不動你的 `data/` |
| smoke | `scripts/smoke.sh` | 與 CI 相同的步驟（會自動換埠） |
| 假 IMAP | `tests/_tpi_imap_fake.py` | 驗證唯讀：指令序列不得出現會改狀態的操作 |
| 假 agent | 既有 `tests/_tpi_*_util.py` 內的本機 CLI 假 agent | 驗證 prompt 內容與 fallback |
| 瀏覽器 | `tests/_tpi_mobile_cdp.js`（Node 22+；沒有就 skip） | 真正的 headless Chrome 檢查 |
| 手動 | `curl` ＋ `/api/health`、`/api/features`、`/dump-dom` | 快速確認路由與畫面 |

寫測試的三個硬性要求：

1. **不得連線到任何正式服務**；需要外部行為就用本機起的暫時服務或檔案。
2. **不得讀寫 repo 以外的路徑**（`tmp_path`／`tempfile`／暫存根目錄都可以）。
3. 需要假憑證時用明顯假字串（例如 `FAKE_VALUE_FOR_TEST`），不要用看起來像真金鑰的格式。

---

## 7. 陷阱清單

1. **import 路徑**：`server/` 底下的模組是頂層模組（`import yhbmail`、`from features import get, post`），不是 `server.yhbmail`。新檔案照抄既有檔的 import 風格。
2. **不要改 `app.py`／`index.html`**：外掛機制已覆蓋絕大多數需求；例外（PWA meta 這類）要最小、雙語、在 PR 說明（ADR 0004）。
3. **清快取不是「清空」**：新表要決定歸屬並更新 `features/cache.py`，否則會誤删使用者資料，或清了又被回填（ADR 0006）。
4. **語言切換會踩到核心覆寫**：核心更新語言時會用 `textContent` 覆寫部分節點，可能吃掉計數用的子節點。模組要自己 `relabel()`，不要依賴別人的 DOM 結構。
5. **重複渲染**：async 載入回來時 `state.view` 可能已經換了。照既有模組的寫法：渲染前後都檢查 `state.view`，並避免同時兩次渲染互蓋。
6. **agent 錯誤不要外露**：例外字串可能夾帶端點回應或 CLI 對 prompt 的回顯。只回類別（必要時附 HTTP 狀態碼），細節寫進本機紀錄就好。
7. **fallback 一定要標**：沒有接 agent 時，畫面上要清楚寫「本機啟發式」，不要讓使用者以為是模型輸出（ADR 0005）。
8. **路徑安全**：由使用者輸入組出的檔名（deliverables、slides）要先正規化再以嚴格樣式驗證，讀取端也要驗證（ADR 0011）。
9. **對外抓取要加倍小心**：ICS 匯入這類功能要有 Origin 檢查、私有位址的明確允許、大小上限、重新導向處理，且不得洩漏私密事件標題。
10. **時間處理**：統一用 `yhbmail.TZ` 與既有時戳格式；行事曆事件帶時區，別用 naive datetime 比較。
11. **FTS5 不一定在**：搜尋要有降級路徑，並在回應裡說清楚現在用哪個引擎（ADR 0003）。
12. **測試隔離**：把根目錄指到暫存目錄（沿用 `tests/_tpi_*.py` 的做法）。不要寫 repo 內的 `data/`，也不要讀使用者的 `vault/`。
13. **信件內容是資料，不是指令**：context pack 的規則已寫明；新 prompt 要沿用「來源文字只能當資料」這條，並要求缺的事實標缺。
14. **示範資料只能虛構**：`example.com` 網域、虛構人名。不要把真實信件片段貼進測試、issue、PR、截圖或文件（ADR 0014）。
15. **不要引入背景服務**：單一行程是硬規則（ADR 0001）；長時間工作做成使用者觸發的批次。
16. **輪詢要有節制**：新信通知靠輪詢，間隔不要縮短到會讓自架伺服器吃重。
17. **`stdout` 是協定通道**：`mcp_server.py` 內任何 debug 輸出都要走 `stderr`，否則客戶端會斷線（ADR 0010）。
18. **快取版本**：改 `ui/` 或 manifest／圖示會影響 service worker 版本，改完在瀏覽器用無痕視窗確認（ADR 0012）。

---

## 8. PR 前自我檢查清單

- [ ] 有沒有任何東西會**離開這台機器**？（寄送、上傳、第三方同步）→ 應該沒有（ADR 0002）
- [ ] 新增的寫入端點有 `local_origin` 檢查與 403 測試嗎？（ADR 0009）
- [ ] 有引入 pip 套件嗎？沒有的話能不能維持（ADR 0003）
- [ ] 新資料是「快取」還是「使用者資產」？`cache.py` 與測試更新了嗎？（ADR 0006）
- [ ] 使用者可見字串 `zh`／`en` 都有嗎？有沒有簡體字？（ADR 0013）
- [ ] 有沒有真實位址、真實人名、真實信件片段、任何憑證值？→ 換成 `example.com`／`FAKE_VALUE_FOR_TEST`（ADR 0014）
- [ ] 測試會連外網或寫到 repo 外的路徑嗎？→ 改成暫存目錄（第 6 節）
- [ ] 動到 `.github/workflows/`、`app.py`、`index.html` 了嗎？→ 應該沒有，或已在 PR 說明
- [ ] `python3 -m unittest discover -s tests` 與 `scripts/smoke.sh` 都綠燈嗎？

---

## 9. 決策文件怎麼用

改動前先掃一眼 [ADR 索引](README.md)。如果這次改動會**推翻**某條 ADR（例如真的要引入第三方套件、要對外開埠、要讓 agent 有副作用），
請**新增**一篇 ADR 說明理由與影響，而不是修改舊文——舊文是歷史，改了就看不出轉折。
文件只放 `docs/fmb-adr/`，不要動 `state/`（那是 orchestrator 的紀錄）或 README 的功能承諾。
