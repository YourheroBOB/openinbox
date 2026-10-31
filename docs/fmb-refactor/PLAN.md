# 重構計畫：目標結構與批次

## 1. 目標結構

```text
server/
  agent_bridge.py              既有；新增公開的單次呼叫介面（completion）
  features/
    agents.py                  HTTP 邊界：路由、輸入驗證、回應組裝
    _deliverables.py           成果儲存：id、路徑、渲染、列出、讀取（新）
    _addr.py                   位址解析共用（新；或改放核心 yhbmail）
    _i18n.py                   語言代碼正規化與雙語取字（新）
ui/modules/
  agents.js                    畫面：任務、成果清單、預覽（拆分後）
```

設計約束：

- 新增的 `_` 前綴模組沿用 repo 既有慣例（`_ics.py`、`_origin.py`、`_outbox_transport.py` 都不註冊路由），避免被功能載入器當成路由模組。
- 不改 `server/app.py`、不改 `ui/index.html`（B6 若獲准才動載入器）。
- 不改任何 JSON 檔、資料庫 schema、fixtures。

## 2. 分批總表

| 批次 | 主題 | 主要檔案 | 可獨立驗證的方式 | 估計 |
|---|---|---|---|---|
| B0 | 基線與守門測試 | `tests/`（新增／擴充） | 新增案例先紅後綠；基線全綠 | 0.5–1 人日 |
| B1 | 公開 Agent 完成介面 | `server/agent_bridge.py`、`features/agents.py` | 契約測試＋`agents` 行為不變 | 1–1.5 人日 |
| B2 | 語言慣例統一 | `features/_i18n.py`（新）、`features/agents.py` | locale 測試＋全綠 | 0.5–1 人日 |
| B3 | 成果儲存層抽出 | `features/_deliverables.py`（新）、`features/agents.py` | roundtrip＋路徑安全測試 | 1–1.5 人日 |
| B4 | `agents.py` 邊界瘦身與文案表格化 | `features/agents.py` | 契約測試＋函式長度守門 | 0.5–1 人日 |
| B5 | `agents.js` 畫面拆分與命名 | `ui/modules/agents.js` | `node --check`＋UI 測試＋人工清單 | 1–2 人日 |
| B6 | 跨模組 UI 共用（選用，需決策） | `ui/index.html` loader、`ui/modules/*.js` | 逐模組載入無回歸 | 2–4 人日 |
| B7 | 文件 parity 與結構清理 | `README*`、`CONTRIBUTING*`、`adapters/*`、`fmb_feature2/` | parity 測試 | 0.5–1 人日 |

排序理由：B1–B4 都只動 `server/features/agents.py` 周邊，彼此可獨立合併；B5 只動 UI，可與 B1–B4 並行；B6、B7 涉及跨檔與決策，放最後。

## 3. 量測指令

每批前後都跑一次，把輸出貼進 PR 描述（唯讀、只用標準函式庫）。

```bash
python3 -m unittest discover -s tests
scripts/smoke.sh
python3 - <<'PY'
import ast, pathlib
for p in sorted(pathlib.Path("server").rglob("*.py")):
    tree = ast.parse(p.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            n = (node.end_lineno or node.lineno) - node.lineno + 1
            if n >= 40:
                print(f"{p}:{node.lineno} {node.name} {n}")
PY
node --check ui/modules/agents.js || echo "node 不在，跳過語法檢查"
```

驗收門檻（B4 之後）：

- `server/features/agents.py` 內沒有任何函式 ≥ 60 行；`mention()` ≤ 35 行。
- `ui/modules/agents.js` 的 `renderPane()` ≤ 25 行，且三個子畫面各自 ≤ 40 行。
- `python3 -m unittest discover -s tests` 全綠，案例數只增不減。

## 4. 批次細節

### B0　基線與守門測試

**目的**：在動任何程式碼前，把現況行為固定成測試，並取得真實的行數與重複清點。

**步驟**

1. 跑基線指令，記錄案例數與耗時。
2. 用 AST 統計取得 `agents.py` 各函式實際行數，回填 `FINDINGS.md` 的估計值（僅在該批 PR 描述記錄，不回寫本目錄以外的檔案）。
3. `grep -rn "agent_bridge\." server/` 清點是否有其他 feature 也在呼叫私有函式，補進 `FINDINGS.md` D7 的待確認項。
4. `grep -rn "function t(\|const t = \|getJSON" ui/modules/` 清點 UI 小工具重複，補進 D5。
5. 新增 characterization 測試（清單見 `TESTS_RISKS.md` §1）。

**驗收**：新增測試在未改程式的現況下全綠；基線指令全綠。

**回滾**：只刪除新增測試檔。

---

### B1　公開 Agent 完成介面

**目的**：讓 feature 不再呼叫 `agent_bridge` 的私有函式，把「四路分派＋fallback＋錯誤標籤」收斂到單一公開介面。

**步驟**

1. 在 `agent_bridge` 新增公開介面（名稱建議 `complete`），回傳固定結構（`text`／`driver`／`fallback`／`error`）。行為與現況一致，包含：失敗或缺 driver 時 `driver` 回 `"local"`、`fallback` 為真、`text` 為空字串。
2. 把 `agents.py::error_label()` 搬進 `agent_bridge`（或讓 `complete` 直接回傳已正規化的錯誤標籤）。先 `grep` 確認沒有其他模組 import 它。
3. `agents.py::run_task()` 改為呼叫新介面，保留原本「text 為空就退回 `_local_brief`」的行為。
4. `triage.py`、`skills.py` 的等價邏輯**不在本批修改**；若 B0 確認存在，另立 B1b。

**驗收**：`POST /api/agents/task` 與 `/api/agents/mention` 的回應鍵集合、fallback 旗標、錯誤標籤格式與改動前一致（由 B0 的契約測試把關）。

**回滾**：`run_task()` 改回直接呼叫私有函式；新介面可留可刪。

**風險**：錯誤標籤若被其他模組共用，搬移會改變字串；B0 的 grep 為前置條件。

---

### B2　語言慣例統一

**目的**：把四種語言表示收斂成一組函式或一個 `_i18n.py`。

**步驟**

1. 新增 `server/features/_i18n.py`：`is_zh(lang) -> bool`、`pack_lang(is_zh: bool) -> "zh-Hant"|"en"`、`pick(is_zh, zh_text, en_text)`。純函式，無狀態。
2. `agents.py` 改用這些函式；`_lang(req)` 保留為薄包裝（回傳 `"zh"`／`"en"` 以維持既有 dict 內容 `lang: "zh"`）。
3. 把 `mentions_alias()` 的 `features.compose` 依賴改成新的 `features/_addr.py`（或核心 `yhbmail`），`compose` 端保留轉呼叫以維持行為。
4. 把延遲 import 移到檔案頂端；若造成循環，改用「僅在 `_addr.py` 與 `_i18n.py` 為無依賴葉節點」的方式打破。

**驗收**：`zh`／`zh-Hant`／`en`／空字串／大小寫混合的輸入，其 `lang` 欄位與文案選擇都與改動前一致（新增 locale 測試）。

**回滾**：`agents.py` 改回原三元運算式；`_i18n.py` 無其他使用者時直接刪除。

**風險**：`_addr.py` 抽離會動到 `compose.py` 的 import 路徑，需確認沒有外部（含測試）直接 import `features.compose.parse_addr` 以外的假設。

---

### B3　成果儲存層抽出

**目的**：把 `DELIV_DIR`、`ID_RE`、路徑組合、三格式渲染、列出與讀取集中到 `features/_deliverables.py`，路由模組只剩編排。

**步驟**

1. 新增 `_deliverables.py`，對外只暴露：`make_id(kind, target)`、`save(card_meta, text, ...)`、`list_cards(limit)`、`read(did, fmt)`、`card_path(did, fmt)`（內部用）。所有路徑都經同一道 `_valid_id()`。
2. `make_id()` 明確處理：非 ASCII 目標、超長目標、空目標、純標點的目標，保證輸出必符合 id 規則（現況是截斷後才檢查，理論上有截斷成不合法值的邊角）。
3. `_render_md()` / `_render_html()` 移入 `_deliverables.py`，並抽出共用的 `_card_head_lines(card)`，讓 MD 與 HTML 表頭只有一份定義。`_render_html()` 再抽出 `_md_lines_to_html(text)`。
4. `agents.py` 的 `task()`／`mention()` 只呼叫 `_deliverables.save(...)`，回應組裝留待 B4。

**驗收**：`save → list → read` 三格式 roundtrip 一致；非法 id（含 `../`、空字串、大寫、81 字元、含空白）一律拒絕且不觸碰檔案系統；HTML 卡在含 `<script>`、`"`、`&` 的輸入下完全轉義。

**回滾**：把函式搬回 `agents.py`；新檔刪除。此批純搬移，回滾成本低。

**風險**：`_render_md()`／`_render_html()` 的輸出若被快照式測試逐字比對（包含空行與標點），表格化表頭會造成差異。做法：先寫「輸出必須包含哪些子字串」的測試，不寫全文快照；若既有測試是全文快照，在該批 PR 說明並放寬為子字串（不得刪除案例）。

---

### B4　`agents.py` 邊界瘦身與文案表格化

**目的**：消除 D1／D2／D6／L2／L3，讓 `agents.py` 成為薄的 HTTP 邊界。

**步驟**

1. `task()` 與 `mention()` 共用 `_result_payload(result, card)` 產生回應欄位；`mention()` 以 `{**payload, "triggered": True, ...}` 疊加。
2. `_local_sources()` / `_thread_source()` 合併為 `_mail_source(item, prefer_body=False)`，保留 snippet 300 字上限。
3. `_local_brief()` 改成資料驅動：`BRIEF_SECTIONS[kind][lang]` 提供段標題與欄位清單，`_brief_lines()` 負責組裝。`LABELS` 補齊「本機資料」「本機啟發式提示」等鍵。
4. `mention()` 抽出 `_resolve_input(req)`（回傳 `via`、`item`、`text`）與 `_infer_kind(parsed, text, rest_line)`，主體只留流程。

**驗收**：`mention()` ≤ 35 行；`/api/agents/task`、`/api/agents/mention`、`/api/agents/deliverables`、`/api/agents/deliverables/<id>.<fmt>` 的狀態碼與鍵集合不變；四種 `via` 分支（text／thread／email-with-alias／email-with-mention）各有測試。

**回滾**：`agents.py` 單檔回滾。

---

### B5　`agents.js` 畫面拆分與命名

**目的**：拆 `renderPane()`、統一名稱、別名改由 API 取得。

**步驟**

1. `renderPane()` 改為分派器，拆成 `panePreview()`、`paneCards()`、`paneTask()`。`paneCards()` 內保留 `await loadCards()` 後對 `state.view`／`view.tab`／`view.preview` 的重檢（現況有這道防護，不可省略）。
2. 別名改由 `/api/agents/deliverables` 回傳的 `alias` 取得並快取；取不到時退回中性字串（例如 `agent`），不要在 UI 硬寫完整位址。
3. `tag-` 前綴統一改為 `agent-`（CSS class 與元素 id 一起改，包含 `tagThreadBox`、`tagMd` 等查詢點）。
4. `pendingPreview` 改名為 `deferredPreview`，並在 `setView` 覆寫處加註解說明用途。
5. 把 `isZh`／`t`／`tf`／`h`／`getJSON`／`postJSON` 的實作維持不變但統一命名與錯誤處理（`postJSON` 一律拋出帶 `.data` 的 Error），為 B6 鋪路。

**驗收**：`node --check ui/modules/agents.js` 通過（無 Node 則跳過）；`tests/test_tpi_agents_ui.py` 全綠；手動清單：深連結 `#view=agents`、thread 內 `@agent`、預覽 MD／HTML、語言切換後重繪、成果清單重新整理。

**風險**：若既有 UI 測試以字串比對 `tag-` 前綴或別名文字，需在同批更新測試字串（屬允許範圍，但要在 PR 說明）。

---

### B6　跨模組 UI 共用（選用）

**目的**：消除 D5。

**前置條件**：確認 `GET /api/ui-modules` 的載入順序可控，且可加入一個非功能的共用檔（需動 `ui/index.html` 或 loader）。**未取得 BOB 同意前不做。**

**步驟**

1. 新增 `ui/modules/_kit.js`（不註冊路由、不建立 nav 按鈕），提供 `isZh`／`makeT(dict)`／`h`／`getJSON`／`postJSON`；掛在單一全域名稱下。
2. 逐模組遷移，一次一個模組、一次一個 PR；遷移後該模組不得再自行定義同名函式。
3. 最後才移除各模組的副本。

**驗收**：每個模組遷移後，其 UI 測試與手動清單都通過；全域只有一份實作。

**風險**：載入順序若不可控，模組會在 `_kit` 尚未定義時執行而整片失敗。回滾方式為單一模組還原。

---

### B7　文件 parity 與結構清理

**目的**：消除 D8；決定 C6（`fmb_feature2/`）。

**步驟**

1. 新增 `tests/test_fmb_docs_parity.py`：對三組雙語文件斷言「兩邊的 Markdown 標題層級與數量一致」與「互相連結存在」，不比較內文（避免脆弱的全文比對）。
2. 修正目前不對稱的章節。
3. `fmb_feature2/` 依 BOB 決策處理：納入 `server/features/`（需走功能載入器的註冊語意與新測試）、保留但加註「暫存區，不被主程式載入」，或移除。**保守預設：先只加註說明，不動程式。**

**驗收**：parity 測試全綠；`python3 -m unittest discover -s tests` 案例數增加且全綠。

## 5. 每批完成定義

1. 該批新增測試先紅後綠，且改動後 `python3 -m unittest discover -s tests` 全綠。
2. `scripts/smoke.sh` exit 0。
3. 公開行為不變，或差異已在 PR 描述逐項列出並有測試覆蓋。
4. 沒有新增寄信路徑、遠端郵件寫入、pip 相依、遙測、對外網路呼叫。
5. 沒有新增或修改 secrets、憑證設定、`.github/workflows`、git remote。
6. 測試只使用 `tempfile`／`tmp_path` 與虛構資料；假憑證一律使用 `FAKE_VALUE_FOR_TEST` 這類明顯假字串。
7. 改動範圍與本批主題一致，不夾帶無關重整。
