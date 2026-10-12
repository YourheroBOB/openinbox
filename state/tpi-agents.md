# tpi-agents

goal: Agent 協作：研究人物／公司、會議準備動作走 BYO agent bridge；在 thread 中 @agent（或寄到 agent 別名）觸發 agent 處理；成果卡片（MD／HTML）可在 app 內預覽。對應 F32 F33。
status: done
next: 等 review／合併。可選後續：deliverable 卡片可寫回 Second Brain（需 BOB 同意，目前不做）；`@research` 目標目前取整行，可加更聰明的人名擷取；email_id 路由目前只讀本機快取，不做收信。

## 功能

- F32 研究與會議準備：`server/features/agents.py`，`POST /api/agents/task`（kind：`research_person`／`research_company`／`meeting_prep`）。context pack 只取本機資料（persona、本機快取信件、second brain），經 `agent_bridge` 的 driver（local／openai_compatible／cli／http）執行；外部 driver 失敗或回空就退回本機啟發式並標 `fallback`＋`error`。
- F33 thread 中 @agent：`POST /api/agents/mention`，`text` 內含 `@agent`／`@research`／`@research-company`／`@prep`／`@meeting` 即觸發；`email_id` 路由本機快取的一封信（收件人含 `agent@example.com` 別名，或內文有 @agent 提及才觸發）。別名只是路由字串，不收發信。
- 成果卡片：每次任務寫入 `data/deliverables/<id>.{md,html,json}`（gitignored）。`GET /api/agents/deliverables`、`GET /api/agents/deliverables/<id>.md|.html|.json` 預覽。HTML 全部 escape、無 script；UI 以 `sandbox=""` iframe 預覽。
- UI：`ui/modules/agents.js`（nav「🤝 代理協作」，繁中／英文）：發動任務（三種 kind＋對象）、@agent 輸入框、成果卡片列表與 MD／HTML 預覽。經 `/api/ui-modules` 自動載入；`server/app.py`、`ui/index.html` 未改。
- 規則：只讀，不寄信、不碰遠端；id 白名單防路徑穿越；POST 走 `_origin.local_origin` 同源檢查；檔案只用標準庫。

## 計畫（round 1，已完成）

1. [medium] 讀既有 agent_bridge／features 機制／測試基礎設施
2. [high] `server/features/agents.py` 核心任務與 driver 退回
3. [max] 安全：id 白名單、HTML escape、同源檢查、硬規則掃描
4. [high] @agent 解析與 email_id 路由
5. [medium] 成果卡片 MD／HTML 與預覽 API
6. [medium] `ui/modules/agents.js` 繁中／英文
7. [medium] 測試 `test_tpi_agents_{core,mention,ui}.py`，全套＋`scripts/smoke.sh`
8. [low] 文件（本檔、DECISIONS）與 commit 到 `agent/tpi-agents`

## log

- 2026-10-12 08:50 第 1 輪開工：讀 state、建 DECISIONS（Q&A 7 題、預設答案，無 needs_bob 題）。確認 BYO agent bridge 與 features 外掛機制已存在。
- 2026-10-12 09:20 實作 F32／F33 核心、成果卡片、UI 模組、三支測試檔（54 個）。修正：@-目標去掉請求動詞（`請幫我查`、`查`），但保留像「查理」這種人名；UI 訊息與輸入框改存 view 狀態，避免重繪時被清掉。
- 2026-10-12 09:40 驗證：`python3 -m unittest discover -s tests` 546 OK（基線 492 + 新增 54）；`scripts/smoke.sh` OK；`node --check ui/modules/agents.js` OK。
- 2026-10-12 09:45 真實瀏覽器驗證（headless Chrome CDP，臨時伺服器）：nav 出現、發動任務產生 HTML 卡片（iframe sandbox 空字串）、@prep／@research 觸發、非 @ 訊息不觸發、MD 預覽、返回、中英切換，無頁面例外；截圖人工檢視版面。
- 2026-10-12 09:50 硬規則掃描：新增檔案無寄信字樣、無部署設定、workflow 無 deploy／publish／release；email 只有 example.com／.example；`server/app.py`、`ui/index.html`、`STATE.md` 未改。
