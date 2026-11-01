# 新進開發者上手指南

> 適用對象：第一次接觸 openinbox 的工程師。目標是半天內能「跑起來、改對地方、不踩雷」。
> 架構現況以 `docs/fmb/ARCHITECTURE.md` 為準；設計理由見 `docs/fmb-adr/`。

## 0. 五分鐘版

TooPowerInbox 是一台**本機優先的郵箱腦**：一個 Python 單行程、零 pip、資料全在本機
（SQLite + 檔案），面板是可安裝 PWA，另有一個 stdio MCP 服務給外部 Agent 呼叫。

動手前先記住五條邊界（理由各有一篇 ADR）：

1. **不預設寄信**：草稿 → 人工確認 → 本機 outbox，Agent 不能繞過（ADR-0003）。
2. **IMAP 唯讀**：只 `EXAMINE`／`BODY.PEEK`，伺服器上連已讀旗標都不動（ADR-0004）。
3. **憑證只從環境變數**：`accounts.json` 出現明文 `password` 會被拒（ADR-0006）。
4. **只綁 `127.0.0.1`**：會改資料的端點要過 `_origin.local_origin`（ADR-0007）。
5. **外掛是受信任程式碼，不是沙箱**；郵件文字永遠是資料，不是指令（ADR-0012、ADR-0005）。

## 1. 環境與啟動

| 步驟 | 指令 | 發生什麼事 |
|---|---|---|
| 安裝 | `./install.sh` | 檢查 Python 3.9+；建立 `data/`、`vault/cards/`；缺少時從 `accounts.example.json`／`agent.example.json` 複製設定（**不覆蓋**既有檔） |
| 啟動 | `./run.sh` | 設 `OPENINBOX_ROOT`、`OPENINBOX_PORT`（預設 8770），前景執行 `server/app.py`；第一次開機載入 `fixtures/` 示範信 |
| 開面板 | http://127.0.0.1:8770/ | 語系切換：左側按鈕或 `?lang=zh-Hant`／`?lang=en` |
| 測試 | `python3 -m unittest discover -s tests` | 標準函式庫 unittest，用拋棄式暫存目錄 |
| Smoke | `scripts/smoke.sh` | Linux 本機跑 CI（`.github/workflows/smoke.yml`）的等價檢查 |
| 遠端主機 | `OPENINBOX_NO_BROWSER=1 ./run.sh` + `ssh -N -L 8770:127.0.0.1:8770 …` | 伺服器仍只聽 loopback，通道是唯一入口 |

不需要 pip、Node、Redis、資料庫伺服器。Node 只在開發時用來 `node --check` 檢查 JS 語法。

## 2. 模組地圖

### 2.1 核心（`server/` 根目錄）

| 檔案 | 角色 | 什麼時候會改到 |
|---|---|---|
| `server/app.py` | HTTP 服務、核心路由、UI 服務、DB 啟動 | 很少；新功能請走外掛，不要改這裡 |
| `server/yhbmail.py` | 郵件脊樑：帳號模型、分類、SQLite 快取、同步協調、搜尋來源 | 改資料模型、同步行為、分類規則 |
| `server/persona.py` | 「更了解你」推論，寫 `vault/persona.json`／`persona.md` | 改人格推論 |
| `server/second_brain.py` | Second Brain 卡片與索引（`vault/`） | 改衍生卡片 |
| `server/agent_bridge.py` | context pack、`agent.json`、四種驅動、`TOOLS`／`invoke_tool` | 加 Agent 工具或驅動 |
| `server/mcp_server.py` | stdio MCP（JSON-RPC 2.0，一行一則） | 加 MCP 工具 |
| `server/features/__init__.py` | 外掛註冊機制（`get`／`post`／`Raw`） | 改擴充契約本身 |

### 2.2 功能外掛（`server/features/*.py`，啟動時自動註冊）

| 領域 | 模組 |
|---|---|
| 快取與外掛管理 | `cache.py`、`plugins.py` |
| 帳號與同步 | `providers.py`、`imap.py` |
| 分流與摘要 | `triage.py` |
| Email Brain | `email_brain.py` |
| 搜尋與聯絡人 | `search.py`、`contacts.py` |
| 撰寫與草稿 | `compose.py` |
| Outbox | `outbox.py`、`_outbox_transport.py` |
| 行事曆 | `calendar.py`、`_ics.py` |
| 郵件操作 | `mailops.py` |
| 追蹤與自動化 | `followup.py`、`rules.py`、`overnight.py` |
| 技能 | `skills.py` |
| Agent 協作 | `agents.py` |
| 用量 | `usage.py` |
| PWA | `mobile.py` |
| 請求安全 | `_origin.py` |

匯入失敗的外掛不會拖垮全域，可在 `GET /api/features` 看到健康狀態與錯誤。

### 2.3 前端

- `ui/index.html`：三欄收件匣、語系切換、鍵盤操作、核心 API、外掛載入器（依 `GET /api/ui-modules` 清單載入）。
- `ui/modules/*.js`：每個功能一個模組，各自內建 `S = { zh: {...}, en: {...} }` 字典。
- `ui/pwa/`：離線頁；`sw.js` 由 `server/features/mobile.py` 提供。

### 2.4 技能、測試與狀態

- `skills/*.md`：雙語技能（繁體中文在前、英文在後），`skills.py` 載入，開關存 `data/skills.json`。
- `fixtures/`：虛構示範資料（信件、ICS、規則）。
- `tests/`：兩支命名族——`test_tpi_<工作包>_*.py` 與 `test_fmb_{contract,edge,integration,prop}_*.py`；共用的假工具在 `tests/_tpi_*.py`（如 `_tpi_imap_fake.py`、`_tpi_server.py`）。
- `state/*.md`：各工作包的 goal／status／next／log；根目錄 `STATE.md` 由 orchestrator 彙整。

### 2.5 本機資料（全部不進 git）

`data/openinbox.db`、`data/usage.jsonl`、`data/contacts.json`、`data/skills.json`、
`data/slides/`、`data/deliverables/`、`vault/persona.*`、`vault/index.json`、
`vault/cards/*.md`（只留 `.gitkeep`）、`accounts.json`、`agent.json`、`rules.json`。

## 3. 請求生命週期與主要資料流

一次 UI 操作的路徑：

```
ui/modules/*.js  fetch
  → server/app.py（核心路由）或 features 外掛（裝飾器註冊的路由）
    → yhbmail（SQLite）／vault／data 檔案
      → 需要模型時：agent_bridge 建 context pack → 外部驅動 或 本機啟發式
  → JSON 回前端（雙語字串由前端字典決定）
```

主要資料流（細節看 `docs/fmb/ARCHITECTURE.md` 第 5 節）：

- **啟動**：`install.sh` → `app.py` → yhbmail 建庫＋載入示範 → persona／second_brain 衍生 → 開 8770。
- **同步**：`accounts.json` → demo fixture／`gog`／`gsk`／IMAP（唯讀）→ 統一格式 → `emails` 表 → 五桶分類；單一帳號失敗只記該帳號狀態，不阻塞他人。
- **收件匣→分流→摘要**：UI 讀 `/api/inbox`（本機快取）→ `triage.py` 整理視圖 → 規則式抽取；有接 Agent 才改寫，失敗標 `fallback`。
- **搜尋**：查詢解析 → FTS5（`unicode61`＋中文重疊 bigram；沒有 FTS5 就退 `LIKE`）→ `search_docs`；刪信會連坐清索引。
- **撰寫→outbox**：`compose.py` 產草稿進 `drafts` 表 → outbox 需確認 token＋`ack` → 到期只移入**本機** outbox → 倒數內可取消，不刪原草稿。
- **技能**：`skills.py` 本機先算 → 有 Agent 才改寫 → 產物落 `data/slides/` 或更新 `data/contacts.json`。
- **Agent 協作**：`POST /api/agents/task`／`/api/agents/mention` → 建 pack（persona＋本機信＋thread）→ 驅動或本機 brief → 存 `data/deliverables/*.{md,html,json}`。
- **MCP**：`server/mcp_server.py` 以 stdio 對外；五個工具只讀快取，`save_draft` 只寫 `drafts` 表。
- **清快取**：`POST /api/cache/clear` 清掉郵件快取、Agent 回合、衍生卡片；**保留**草稿、手寫卡片、本機／匯入行事曆（含 `cal_feeds`）；`{"reseed": true}` 重建示範。

## 4. 常見修改路徑

### 4.1 加一個 API 端點

1. 新增 `server/features/<name>.py`（不要改 `server/app.py`）。
2. `from features import get, post, Raw`；用裝飾器註冊；請求物件提供 `req.query`、`req.body`、`req.lang_zh()`；非 JSON 回應用 `Raw`。
3. **會改資料或暴露本機資料的端點**，開頭做 `if not local_origin(req): return refuse(req.lang_zh())`（參考 `features/agents.py`）。
4. 需要模型就走 `agent_bridge` 並保留「失敗→本機啟發式＋fallback 旗標」。
5. 錯誤只回例外類型與 HTTP 狀態碼（`error_label` 模式，見 ADR-0014）。
6. 補 `tests/test_tpi_*_*.py`：用 `tmp_path`／`tempfile`、假資料、`FAKE_VALUE_FOR_TEST`。

### 4.2 加一個 UI 面板

1. 新增 `ui/modules/<name>.js`：IIFE、`S = { zh, en }`、`window.__tpiXxx` 守衛防重複載入、注入 `<style>`、加 nav 按鈕、監聽 `lang` 變更重繪（完整範本看 `ui/modules/agents.js` 的 `MutationObserver` 用法）。
2. 所有使用者可見字串進兩個語言字典；**禁止簡體**。
3. 任何外部內容先 `h()` 轉義；HTML 預覽用 `sandbox=""` iframe；MD 用 `textContent`。
4. 不改 `ui/index.html`，靠 `GET /api/ui-modules` 自動載入。

### 4.3 加一個技能

放 `skills/<name>.md`（繁中在前、英文在後）。`GET /api/skills` 會出現；執行開關在 `data/skills.json`，關閉的技能會拒絕執行。

### 4.4 加一個 Agent 工具

`agent_bridge.TOOLS` 放工具描述、`invoke_tool` 放實作（CONTRIBUTING 明言）。MCP 若要暴露，需同步 `server/mcp_server.py` 的工具清單（目前固定五個）。

### 4.5 加一種 Agent 驅動

在 `agent_bridge` 的 driver 分派加一支，更新 `adapters/README*.md`；保留本機後備與 fallback 標示；新驅動同樣遵守 ADR-0014 的錯誤淨化。

### 4.6 改資料庫 schema

在 yhbmail 的初始化／遷移路徑加**可回復、可驗證**的遷移；測試用暫存根目錄重建；動到 `mail_state` 這類本機覆寫狀態時，確認再次同步不會抹除使用者操作。

### 4.7 改快取／衍生一致性

任何「郵件改了，什麼要失效」的規則，先讀 `docs/fmb/ROADMAP.md` 第 2 項；新衍生資料請記錄來源簽章，讓舊快取不會命中新內容。

## 5. 陷阱與紅線（送出前對一遍）

**安全邊界**

- [ ] 沒有新增預設寄送路徑；沒有 Agent 工具能繞過人工確認。
- [ ] 會改資料的端點有 `local_origin` 檢查。
- [ ] 不讀寫明文密碼；新憑證一律走環境變數＋`*_env`；測試只用 `FAKE_VALUE_FOR_TEST`。
- [ ] 錯誤訊息、log、usage 不含郵件內文、提示詞、模型回答、金鑰、外部端點原始回應。
- [ ] 落檔 ID 先過嚴格正則；HTML 全轉義、無 script／外部資源；預覽用 sandbox iframe。
- [ ] 郵件主旨／內文／引用一律視為資料；context pack 的反提示注入條款不可刪。
- [ ] service worker 不快取 `/api/*`。

**資料正確性**

- [ ] IMAP 只發 `EXAMINE`／`BODY.PEEK`；不要加 `STORE`、`EXPUNGE` 等寫入命令。
- [ ] 衍生流程可重入（重跑不產生重複卡片）；清快取後可 reseed 重現。
- [ ] FTS5 可能不存在：搜尋在 `LIKE` 模式也要正確，測試涵蓋兩種路徑。
- [ ] 注意 SQLite 寫入競爭；批次操作先鎖定目標清單。
- [ ] `accounts.json` 明文 `password` 要被拒——別為了方便鬆掉這條。

**工程慣例**

- [ ] `server/` 只用標準庫；不加 pip（選配轉接頭除外，且要講清楚）。
- [ ] UI 字串 zh／en 成對；禁止簡體。
- [ ] 測試用 `tmp_path`／`tempfile` 與虛構資料；不連正式服務。
- [ ] 不 commit `data/`、`vault/`（`.gitkeep` 除外）、`accounts.json`、`agent.json`、`rules.json`。
- [ ] 不改 `.github/workflows`、secrets／憑證設定、git remote；不 push／merge。
- [ ] 架構決策先寫 `docs/fmb-adr/`，再動 code。

## 6. 測試與文件契約

- 新行為補 unittest；UI 語法用 `node --check`（Node 缺席時相關測試跳過，Python 核心測試不可依賴瀏覽器）。
- 行為變更要同步 README／ARCHITECTURE／RUNBOOK；方向性決策進 ADR；待辦進 ROADMAP 或 `state/`。
- 錯誤訊息不得包含郵件內容、案件資料、憑證或外部端點原始回應（ROADMAP 完成定義第 9 條）。

## 7. 延伸閱讀

- `docs/fmb/ARCHITECTURE.md`：現況架構（第 5 節資料流最好用）
- `docs/fmb/ROADMAP.md`：下一步與決策閘門
- `docs/fmb/RUNBOOK.md`：維運手冊
- `docs/fmb-adr/README.md`：ADR 索引
- `docs/fmb-security/`、`docs/fmb-perf/`、`docs/fmb-review/`：安全、效能與審查報告
- `CONTRIBUTING*.md`、`README*.md`、`adapters/README*.md`、`state/`
