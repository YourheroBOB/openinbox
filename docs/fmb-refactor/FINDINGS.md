# 調查結果：重複、過長、耦合、命名

信心等級：**已確認**＝本次讀過完整原始碼；**待確認**＝依 `docs/fmb/ARCHITECTURE.md`、repo 檔案清單或命名慣例推定，需在 B0 清點。

## 0. 摘要

| 類別 | 編號 | 一句話 | 批次 |
|---|---|---|---|
| 重複程式 | D1 | `task()` 與 `mention()` 手工組出同一組回應欄位 | B4 |
| 重複程式 | D2 | 兩種來源正規化函式產生同構 dict | B4 |
| 重複程式 | D3 | 卡片路徑拼接分散在三處 | B3 |
| 重複程式 | D4 | MD／HTML 卡片渲染各自重算語言與表頭 | B3 |
| 重複程式 | D5 | UI 小工具函式在每個 `ui/modules/*.js` 各一份 | B6（選用） |
| 重複程式 | D6 | 雙語三元運算式散落在多個函式 | B2／B4 |
| 重複程式 | D7 | Agent 驅動派送＋fallback 邏輯在多個 feature 重寫 | B1 |
| 重複程式 | D8 | 三組雙語文件手動同步 | B7 |
| 過長函式 | L1 | `ui/modules/agents.js::renderPane()` 混合三種畫面 | B5 |
| 過長函式 | L2 | `agents.py::mention()` 混合驗證、解析、執行、回應 | B4 |
| 過長函式 | L3 | `agents.py::_local_brief()` 內嵌六段字面文案 | B4 |
| 過長函式 | L4 | `agents.py::_render_html()` 行內 CSS ＋ 逐行轉換 | B3 |
| 耦合過緊 | C1 | feature 直接呼叫 `agent_bridge` 的私有函式 | B1 |
| 耦合過緊 | C2 | `features.agents` 依賴 `features.compose` 的內部函式 | B2 |
| 耦合過緊 | C3 | 延遲 import 把依賴藏在函式內 | B2 |
| 耦合過緊 | C4 | UI 模組 monkey-patch 全域函式，載入順序敏感 | B5 |
| 耦合過緊 | C5 | 儲存層責任（目錄、id 規則）長在路由模組裡 | B3 |
| 耦合過緊 | C6 | `fmb_feature2/` 平行套件與 `server/features/` 關係不明 | B7（需決策） |
| 命名不一致 | N1 | 語言代碼有四種表示 | B2 |
| 命名不一致 | N2 | agent 別名在 server 有常數、在 UI 硬寫 | B5 |
| 命名不一致 | N3 | result／card／deliverable 三名詞混用 | B3／B4 |
| 命名不一致 | N4 | `did` 與 `id` 混用 | B3 |
| 命名不一致 | N5 | `agents.js` 的 CSS class 與 id 用 `tag-` 前綴 | B5 |
| 命名不一致 | N6 | `pendingPreview` 未表達跨畫面傳遞語意 | B5 |
| 命名不一致 | N7 | `_local_sources` / `_thread_source` 單複數與語意不對稱 | B4 |
| 命名不一致 | N8 | `build_pack` / `context_pack` / `run_task` 命名層次不清 | B1 |

---

## 1. 重複程式

### D1　HTTP 回應組裝重複（已確認）

`server/features/agents.py` 的 `task()` 與 `mention()` 各自手寫同一組欄位：

```python
return {"deliverable": card, "text": result["text"], "driver": result["driver"],
        "fallback": result["fallback"], "error": result["error"], "sources": result["sources"]}
```

`mention()` 版本只是多三個鍵（`triggered`、`via`、`mention`）。任何新增欄位都必須改兩處，容易漏。

**影響**：契約漂移風險；測試若只斷言其中一端的鍵集合，另一端的漂移不會被發現。

### D2　來源正規化重複（已確認）

`_local_sources()` 與 `_thread_source()` 產生完全同構的 dict（`id`／`subject`／`from`／`date`／`snippet`），差別只在 snippet 取 `body_text` 或 `snippet`。可合併為單一 `_mail_source(item, prefer_body=False)`。

### D3　卡片路徑拼接分散（已確認）

`DELIV_DIR / f"{did}.{fmt}"` 這個組法出現在 `save_deliverable()`（兩次，md/html/json）、`read_deliverable()`、`list_deliverables()`（glob 後檢查 stem）。id 驗證則散在 `_valid_id()`、`save_deliverable()` 的長度截斷、`read_deliverable()` 的 fmt 白名單。路徑安全檢查沒有單一入口。

### D4　MD／HTML 卡片渲染各自重算（已確認）

`_render_md()` 與 `_render_html()` 都先算 `zh = card["lang"] == "zh"`、`lab = LABELS[...]`，再各自拼「類型／產出時間／驅動」三個中繼欄位。`save_deliverable()` 又用第三種寫法組標題。三處對「卡片表頭」的定義必須同步修改。

### D5　UI 小工具函式重複（agent.js 已確認，其他模組待確認）

`ui/modules/agents.js` 自帶 `isZh()`、`t()`、`tf()`、`h()`、`getJSON()`、`postJSON()`，並各自處理 `{placeholder}` 取代與錯誤拋出。依 `docs/fmb/ARCHITECTURE.md` 所述「每個 `ui/modules/*.js` 都要有 zh 與 en 字串」，其他模組很可能有等價副本（待 B0 清點）。

**保守做法**：B6 只在能安全改動 `ui/index.html` 的模組載入器時才做共用；否則只統一命名與行為，不強制抽檔。

### D6　雙語三元運算式散落（已確認）

`_local_brief()` 一個函式內就有三組 `... if zh else ...` 六段字面文案；`save_deliverable()` 的標題、`_local_brief()` 的結尾提示各一組。`LABELS` 只涵蓋部分字串，形成「一半表格化、一半行內」的混用。

### D7　Agent 驅動派送＋fallback 重複（agents.py 已確認；triage.py／skills.py 待確認）

`run_task()` 內手寫四路分派並呼叫 `agent_bridge` 的私有函式，再接一段 fallback：

```python
if driver == "openai_compatible":
    text = agent_bridge._openai(pack, cfg).strip()
elif driver == "cli":
    text = agent_bridge._cli(pack, cfg).strip()
elif driver == "http":
    text = agent_bridge._http(pack, cfg).strip()
else:
    used, fallback = "local", True
```

依 `docs/fmb/ARCHITECTURE.md` §5.3「外部 Agent 失敗、逾時或回傳空白時，結果退回本機啟發式」與 §9 的降級表，`triage.py`、`skills.py` 應有等價邏輯，待 B0 以 `grep -rn "agent_bridge\." server/` 清點確認。

### D8　雙語文件成對維護（已確認）

`README.md`／`README.zh-Hant.md`、`CONTRIBUTING.md`／`CONTRIBUTING.zh-Hant.md`、`adapters/README.md`／`adapters/README.zh-Hant.md` 三組皆為手動同步，沒有 parity 檢查。目前內容大致對齊，但章節增減容易只改一邊。

---

## 2. 過長函式

行數為估計值，B0 以 AST 統計回填實際數字。

| 編號 | 位置 | 估計 | 混在一起的責任 |
|---|---|---:|---|
| L1 | `ui/modules/agents.js::renderPane()` | ~70 行 | 預覽畫面／成果清單／任務表單三種畫面＋awaited fetch 後的狀態重檢 |
| L2 | `agents.py::mention()` | ~45 行 | origin 檢查、三種輸入來源判定（text／thread／email）、別名路由、kind 推斷、執行、回應 |
| L3 | `agents.py::_local_brief()` | ~35 行 | 語言切換、來源列表、三種 kind 的段落模板、結尾提示 |
| L4 | `agents.py::_render_html()` | ~30 行 | 行內 CSS、Markdown 逐行轉 HTML、表頭 |

`mention()` 的複雜點並非行數本身，而是三個 `via` 分支與 `parsed` 的三段補值交錯，測試難覆蓋（見 `TESTS_RISKS.md` 的案例清單）。

---

## 3. 耦合過緊

### C1　呼叫 `agent_bridge` 私有函式（已確認）

`agents.py::run_task()` 直接呼叫 `_openai`／`_cli`／`_http`。這使得 `agent_bridge` 無法安全重構內部簽章，任何 rename 都會波及 feature 層。建議在 `agent_bridge` 新增公開的完成介面（例如 `complete(pack, cfg=None)` 回傳含 `text`／`driver`／`fallback`／`error` 的結果物件），feature 只依賴公開介面。

### C2　feature → feature 內部依賴（已確認）

`mentions_alias()` 內 `from features.compose import parse_addr, split_addrs`。位址解析屬於通用工具，放在 compose feature 內迫使 agents 依賴另一個功能的內部實作。建議移到共用模組（與 `_ics.py`、`_origin.py` 同層的 `_addr.py`，或核心 `yhbmail`），並保留 compose 的對外行為。

### C3　延遲 import 隱藏依賴（已確認）

`build_pack()` 內 import `agent_bridge.context_pack` 與 `persona.load`；`run_task()` 內 import `agent_bridge`；`mentions_alias()` 內 import `features.compose`。這些延遲 import 可能是為了避開載入順序或循環，但代價是依賴關係在檔案頂端看不出來，也讓「這個模組會不會連網／讀哪個目錄」變得不可一眼判斷。重構時應改為頂端 import，並以測試證明無循環。

### C4　UI 全域 monkey-patch（已確認）

`ui/modules/agents.js` 覆寫 `window.openThread` 與 `window.setView`，並用 `MutationObserver` 監看 `document.documentElement` 的 `lang` 屬性。行為正確但高度依賴「核心先載入、外掛後載入」的順序；任何載入順序變動或核心函式改名都會靜默失效。

### C5　儲存層責任長在路由模組（已確認）

`DELIV_DIR`、`ID_RE`、`_valid_id()`、三種格式渲染、列出與讀取都在 `features/agents.py`。路由與持久化混在同一檔，導致 D3 的路徑安全檢查分散。建議抽出 `server/features/_deliverables.py`（沿用既有 `_` 前綴慣例：`_ics.py`、`_origin.py`、`_outbox_transport.py`）。

### C6　`fmb_feature2/` 平行套件（待確認）

`fmb_feature2/__init__.py` 自述「copy the modules into server/features/ when you want them wired up」，`feature_imap_mailbox.py` 用 try/except 保護 import。這是一個未被主程式載入的平行目錄，與 `server/features/` 形成兩套慣例。是否納入或移除需 BOB 決策（見 `TESTS_RISKS.md`）。

---

## 4. 命名不一致

### N1　語言代碼四種表示（已確認）

- `req.lang_zh()` → bool
- `agents.py::_zh(lang)` → 以 `startswith("zh")` 判斷 → bool
- `agents.py::_lang(req)` → `"zh"` / `"en"`
- `build_pack()` 再轉成 context pack 的 `"zh-Hant"` / `"en"`

四個名稱、三種型別語意。新增語言或修正 `zh-tw` 之類輸入時，很容易只改到其中一層。

### N2　agent 別名（已確認）

`agents.py` 有 `ALIAS = "agent@example.com"`，而 `ui/modules/agents.js` 在提示文字中硬寫同一個字串。諷刺的是 `/api/agents/deliverables` 已經回傳 `alias` 欄位，UI 卻沒使用。別名只要改一次就會不一致。

### N3　result／card／deliverable（已確認）

同一個概念在三個層次用三個名詞：執行輸出叫 `result`，落地後的 dict 叫 `card`，API 對外叫 `deliverable`。目前可靠 context 分辨，但新進者需要讀完三個函式才知道關係。

### N4　`did` 與 `id`（已確認）

內部變數 `did`、函式參數 `did`、dict 鍵 `id`、URL 段落變數 `did`。建議統一為 `deliverable_id`（長）或 `id`（dict 鍵），並在 `_deliverables.py` 對外只接受 `did` 一種寫法。

### N5　`tag-` 前綴（已確認）

`ui/modules/agents.js` 的 CSS class（`.tag-tabs`、`.tag-form`、`.tag-out`…）與元素 id（`tagTarget`、`tagMention`、`tagThreadText`、`tagMd`、`tagThreadBox`、`tagMsg`、`tagResult`、`tagMentionMsg`）全用 `tag-` 前綴，與模組名 `agents` 不符，疑似沿自舊功能。改名需同步 CSS、HTML 字串、`id` 查詢與可能的 UI 測試字串。

### N6　`pendingPreview`（已確認）

欄位語意是「在 thread 內產生卡片後，等 `setView("agents")` 時才顯示的預覽」。名稱只表達「待處理」，未表達跨畫面傳遞。

### N7　來源函式命名（已確認）

`_local_sources`（複數、回傳 list）與 `_thread_source`（單數、回傳 dict）並列，讀者會誤以為兩者層級不同；實際上前者是後者的迴圈包裝。

### N8　pack／task／run 命名層次（已確認）

`agent_bridge.context_pack()`、`agents.build_pack()`、`agents.run_task()`，加上計畫新增的 `agent_bridge.complete()`，需明確定義：context pack＝輸入材料；pack＝任務專用材料；run＝含 fallback 的執行；complete＝單次模型呼叫。建議在 `agent_bridge` docstring 與 `PLAN.md` 的詞彙表寫清楚。

---

## 5. 詞彙表（重構後的建議用語）

| 詞 | 定義 |
|---|---|
| context pack | `agent_bridge.context_pack()` 產生的通用材料（人格、看板、近期信、技能） |
| task pack | 加入任務目標與來源後的專用材料（目前叫 `build_pack()` 的輸出） |
| completion | 一次模型呼叫的結果：`text`／`driver`／`fallback`／`error` |
| deliverable | 落地的成果（md／html／json 三檔＋metadata） |
| deliverable id | 符合嚴格格式的識別碼，唯一能用來組路徑的值 |
| agent alias | 僅供 thread 路由辨識的字串，永不投遞 |
