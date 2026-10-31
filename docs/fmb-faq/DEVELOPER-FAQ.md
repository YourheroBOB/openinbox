# 開發者常見問題（D1–D9）

適用對象：要加功能、改 UI、寫測試或接外部 Agent 的人。
先讀 `CONTRIBUTING.zh-Hant.md` 與 `docs/fmb/ARCHITECTURE.md` 的「API 與擴充契約」一節，再看本頁。

---

## D1. 怎麼新增一個後端功能？一定要改 `server/app.py` 嗎？

**問題**：想加一支 API，但不確定註冊流程。

**原因**：專案採「模組化單體 + 外掛路由」，`features` 套件在匯入時自動註冊裝飾器。

**解法**：新增 `server/features/<name>.py`：

```python
from features import get, post

@get("/api/hello")
def hello(req):          # req.query、req.body、req.lang_zh()
    return {"hello": "world"}
```

- 需要回傳非 JSON（HTML、bytes）時用 `from features import Raw`。
- `server/app.py` 不需要改；`GET /api/features` 會列出已載入功能、路由與載入錯誤。
- 新外掛在同一行程內執行，屬**受信任程式碼**，不是沙箱。
- 會改變資料的端點請先過 `features/_origin.py` 的本機來源檢查（見 D3）。

**相關檔案**：`server/features/__init__.py`、`server/features/plugins.py`、`server/features/agents.py`（完整範例）

---

## D2. 怎麼新增前端模組？字串規則有哪些？

**問題**：加了一個功能，但側欄／面板沒出現。

**原因**：UI 由 `index.html` 的單一 loader 依 `GET /api/ui-modules` 自動載入 `ui/modules/*.js`。

**解法**：
1. 新增 `ui/modules/<name>.js`，沿用既有模組的寫法（建立側欄按鈕、`dataset.view`、`window.setView` 掛鉤、`MutationObserver` 監聽 `lang` 變化）。
2. **每個介面字串都要有 `zh` 與 `en`**，且 `zh` 必須是繁體中文，禁止簡體。
3. 不要自己改 `ui/index.html` 去硬載入模組。
4. 除錯時依序檢查 `GET /api/ui-modules` 是否列出你的檔案、`/ui/modules/<name>.js` 是否 200、`node --check` 是否通過。

**相關檔案**：`ui/modules/agents.js`、`server/features/plugins.py`、`CONTRIBUTING.zh-Hant.md`

---

## D3. 為什麼我的 POST 從 curl／腳本送出會被拒？

**問題**：本機打的 POST 端點回錯誤，面板按卻正常。

**原因**：會變更資料的端點用 `features/_origin.py` 的 `local_origin(req)` / `refuse(req.lang_zh())` 檢查請求是否來自在 `127.0.0.1` 開啟的面板。

**解法**：
1. 新增變更型端點時，照 `server/features/agents.py` 的模式先檢查來源，不通過就 `refuse(...)`。
2. 手動測試時，先從面板操作或讓請求帶上正確的 `Origin`；純後端腳本測試可直接呼叫功能函式（如 `run_task`、`save_deliverable`）避開 HTTP 層。
3. 唯讀端點不需要這層檢查，但也不要因此回傳敏感內容。

**相關檔案**：`server/features/_origin.py`、`server/features/agents.py`、`tests/_tpi_server.py`

---

## D4. 測試怎麼跑？可以連真信箱或真 Agent 嗎？

**問題**：不確定測試的邊界，怕動到正式資料。

**原因**：測試套件刻意全部離線、可拋棄。

**解法**：
1. `python3 -m unittest discover -s tests`（標準函式庫 `unittest`）；`scripts/smoke.sh` 跑與 CI 相同的 smoke 檢查。
2. 測試一律用 `tempfile`／`tmp_path` 之類的拋棄式資料夾，不讀寫 repo 以外的路徑，也不連正式服務。
3. 郵件用假 IMAP 伺服器（`tests/_tpi_imap_fake.py`）、示範資料用 `fixtures/`，Agent 用本機 python CLI 假 agent。
4. 需要假憑證時用 `FAKE_VALUE_FOR_TEST` 這種明顯假字串，不要用 `sk-`、`ghp_`、`xox` 等真實格式前綴。

**相關檔案**：`tests/`、`scripts/smoke.sh`、`.github/workflows/smoke.yml`、`CONTRIBUTING.zh-Hant.md`

---

## D5. UI 相關測試需要 Node.js 嗎？

**問題**：CI／本機沒裝 Node，擔心測試紅燈。

**原因**：Node 只用來做 `node --check` 的 JavaScript 語法檢查。

**解法**：Node 缺席時，這類 UI 語法檢查會被跳過，不影響 Python 核心測試與伺服器執行。核心功能不需要 npm、Node、Redis 或任何資料庫伺服器。

**相關檔案**：`tests/test_tpi_mobile_*.js`、`tests/test_tpi_*_ui.py`、`docs/fmb/ARCHITECTURE.md`（7.1）

---

## D6. 搜尋索引是怎麼做的？中文查不到怎麼辦？

**問題**：新增或刪信後搜尋結果不對，中文查詢命中率低。

**原因**：搜尋是兩層策略——優先用 FTS5，沒有 FTS5 就退回 `LIKE`。

**解法**：
1. FTS5 英文用 `unicode61`，中文用重疊 bigram；搜尋前依內容簽章做增量更新，刪信時以 trigger 同步移除索引。
2. 若 Python 的 SQLite 沒編 FTS5，會自動退回 `LIKE`：結果仍正確，但大資料集較慢，不是壞掉。
3. 索引疑似落後時打 `POST /api/search/reindex` 重建。
4. 查詢解析器支援寄件人、日期、附件、已讀、類別、帳號、排除字與引號片語；接上 BYO Agent 時，Agent 只負責把自然語言改寫成運算式，實際搜尋仍由本機索引完成。

**相關檔案**：`server/features/search.py`、`server/features/contacts.py`、`docs/fmb/ARCHITECTURE.md`（5.4）

---

## D7. BYO Agent 有哪些 driver？新工具要加在哪？

**問題**：想換模型或加一個工具給外部 Agent 用。

**原因**：`agent_bridge` 抽象了四種驅動與工具清單。

**解法**：
1. `agent.json` 的 `driver` 可為 `local`（零網路，永遠可用作後備）、`openai_compatible`、`cli`（context pack 從 stdin 進）、`http`（POST context pack，回 `{"answer": "…"}`）。
2. 新工具加在 `agent_bridge.TOOLS` 與 `invoke_tool`。
3. MCP 端（`server/mcp_server.py`）目前有五個工具：`list_inbox`、`brain_board`、`search_brain`、`persona`、`save_draft`；`save_draft` 是唯一寫入工具。要擴充請保持向後相容並補協定測試。
4. 任何新工具都不得開放寄信，也不得繞過人工確認。

**相關檔案**：`agent.example.json`、`server/agent_bridge.py`、`server/mcp_server.py`、`adapters/README.zh-Hant.md`、`tests/test_tpi_mcp_stdio.py`

---

## D8. 為什麼 Agent 錯誤訊息只有例外類別跟 HTTP 狀態碼？

**問題**：想看到完整錯誤，卻只有 `TimeoutError: HTTP 504` 之類的短標籤。

**原因**：這是刻意的遮蔽。`agents.error_label()` 只保留例外類別與可解析出的 HTTP 狀態碼，因為 `agent_bridge` 的例外訊息可能夾帶外部端點回應內容，或 CLI stderr 回顯的提示詞（裡面可能有郵件內文）。

**解法**：
1. 不要為了方便而把 `str(exc)` 直接回給前端或寫進日誌。
2. 需要細節時在**本機**看端點或 CLI 自己的日誌，並確認日誌不會被 commit（`*.log` 已在 `.gitignore`）。
3. 新程式沿用同樣原則：錯誤訊息不得含郵件內文、憑證或外部端點原始回應。

**相關檔案**：`server/features/agents.py`（`error_label`）、`server/agent_bridge.py`、`docs/fmb/ROADMAP.md`（共同完成定義第 9 點）

---

## D9. 成果卡片存在哪？ID 與 HTML 有什麼安全規則？哪些 API 算外部契約？

**問題**：想讀取或新增 Agent 成果檔案，也想知道哪些 API 可以放心整合。

**原因**：Agent 協作把成果寫成本機檔案，並用嚴格 ID 檢查避免路徑穿越。

**解法**：
1. 成果寫在 `data/deliverables/<id>.md`、`.html`、`.json`（`data/` 已被 gitignore）。
2. ID 必須符合 `^[a-z0-9][a-z0-9-]{2,80}$`；讀取端點 `/api/agents/deliverables/<id>.<md|html|json>` 不合法或不存在一律 404，不會組出任意路徑。
3. HTML 卡片全部轉義、不含 script、外部資源或 inline event handler；前端用 sandbox iframe 預覽。
4. 對外契約以 `/api/v1/tools`、`/api/v1/context`、`/api/v1/agent/run` 與 MCP 工具為準；SQLite 資料表名稱（例如 `agent_turns`、`triage_tasks`）屬內部實作，不應被外部整合依賴。
5. `@agent` 的 alias（`agent@example.com`）只是路由字，程式不會投遞任何信給它。

**相關檔案**：`server/features/agents.py`、`ui/modules/agents.js`、`docs/fmb/ARCHITECTURE.md`（5.7、6.1）
