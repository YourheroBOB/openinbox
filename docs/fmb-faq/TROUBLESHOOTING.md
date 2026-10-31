# 疑難排解（T1–T13）

排法：先看症狀，再看原因與解法。每題最後列出相關檔案，方便直接追程式。
若症狀與此處不符，請以 `python3 -m unittest discover -s tests` 與 `scripts/smoke.sh` 的結果為基準回報。

---

## T1. `./run.sh` 之後瀏覽器打不開 8770

**症狀**：連線被拒、頁面一直轉圈；終端機可能已經有 traceback。

**原因**：（a）8770 已被其他程序占用；（b）伺服器啟動失敗（例如 Python 版本不足、`accounts.json` 解析錯誤）；（c）你從別台機器直接連 8770。

**解法**：
1. 先確認服務活著：`curl -s http://127.0.0.1:8770/api/health`。
2. 換埠重跑：`OPENINBOX_PORT=8771 ./run.sh`，開 `http://127.0.0.1:8771/`。
3. 看終端機輸出，不要只看瀏覽器；`install.sh` 會檢查 Python 3.9 以上。
4. 遠端主機請走 SSH 通道（`ssh -N -L 8770:127.0.0.1:8770 …`），不要嘗試直連，也不要改成對外綁定。

**相關檔案**：`run.sh`、`install.sh`、`server/app.py`

---

## T2. 面板打開了，但側欄少按鈕、某個功能整塊不見

**症狀**：主介面正常，個別功能沒有入口或一片空白。

**原因**：該功能的 `server/features/*.py` 匯入失敗，或對應的 `ui/modules/*.js` 404／有語法錯誤，或被 loader 略過。

**解法**：
1. `GET /api/features` 看已載入功能、路由與**載入錯誤**（錯誤訊息不應含郵件內容）。
2. `GET /api/ui-modules` 確認清單裡有沒有你的模組檔名。
3. 直接開 `/ui/modules/<name>.js` 看是否 200。
4. 有 Node 時跑 `node --check ui/modules/<name>.js`。
5. 只壞一個外掛不該拖垮核心；若整個服務起不來，先暫時把該功能檔移出 `server/features/` 再啟動確認。

**相關檔案**：`server/features/plugins.py`、`server/features/__init__.py`、`ui/index.html`

---

## T3. 切成繁中，畫面還是英文（或出現簡體字）

**症狀**：按了「繁中」但部分區塊沒變；或看到不該出現的簡體字。

**原因**：新模組的字串表少了 `zh` 鍵、鍵名不一致，或誤用了簡體字串。

**解法**：
1. 每個 UI 字串都要在 `zh` 與 `en` 兩份表裡都存在，鍵名一致。
2. `zh` 一律繁體中文，禁止簡體（`CONTRIBUTING` 明文規定）。
3. 用 `?lang=zh-Hant` 直接驗證，排除切換按鈕本身的問題。
4. 動態文字（例如成果卡片標籤）也要走同一套字串表，不要硬寫字面值。

**相關檔案**：`ui/modules/agents.js`、`CONTRIBUTING.zh-Hant.md`、`ui/index.html`

---

## T4. 收件匣是空的（明明之前有示範信）

**症狀**：清單 0 封，但服務正常。

**原因**：先前執行過「清除本機快取」且沒有 reseed，郵件快取被移除。

**解法**：
1. `GET /api/cache` 看目前快取狀態。
2. `POST /api/cache/clear` 帶 `{"reseed": true}` 重新載入示範信；或直接按面板的清除快取（含重新載入）。
3. 若是 live 模式，改按「重新整理」觸發同步，並用 `GET /api/providers` 看每個帳號的上次同步結果。

**相關檔案**：`server/features/cache.py`、`ui/modules/cache.js`、`fixtures/demo_inbox.json`

---

## T5. 某個 IMAP 帳號一直顯示「缺密碼」

**症狀**：其他帳號正常，單一帳號同步不了，提示缺少環境變數。

**原因**：`password_env` 指定的變數不存在，或預設推導出的 `TPI_IMAP_PASSWORD_<...>` 名稱與實際 export 的不一致；也可能是 export 在另一個 shell，伺服器沒吃到。

**解法**：
1. 在**啟動伺服器的那個 shell** export，再 `./run.sh`。
2. 預設命名規則是信箱大寫、非英數換成 `_`；`me@example.com` → `TPI_IMAP_PASSWORD_ME_EXAMPLE_COM`。
3. 也可以在 `accounts.json` 明確寫 `"password_env": "TPI_IMAP_ICLOUD_PASSWORD"`，讓名稱不必推導。
4. iCloud 要用 App 專用密碼。
5. `GET /api/providers` 只會回環境變數**名稱**，不會回值。

**相關檔案**：`server/features/imap.py`、`server/features/providers.py`、`ui/modules/providers.js`

---

## T6. IMAP 登入失敗、TLS 錯誤或連線逾時

**症狀**：「測試連線」失敗，或同步整個帳號掛掉。

**原因**：（a）用到登入密碼而非 App 專用密碼；（b）`host`／`port`／`security` 與服務商不符；（c）憑證驗證或系統時間問題；（d）網路或防火牆封鎖 993／143。

**解法**：
1. 先用「測試連線」（`POST /api/providers/check`），它只做登入＋`EXAMINE`，不會下載大量資料。
2. 先用 `provider` 預設值（`icloud`／`fastmail`／`yahoo`／`zoho`）；其他服務商才自填 `host`／`port`，預設 993 SSL，`security` 可設 `starttls`，`none` **只限 loopback**。
3. 檢查系統時鐘與 CA 憑證；憑證驗證不要關掉當成解法。
4. 一個帳號失敗不應影響其他帳號；用 `GET /api/providers` 逐帳號確認上一次的同步結果。

**相關檔案**：`server/features/imap.py`、`server/features/providers.py`、`tests/_tpi_imap_fake.py`

---

## T7. 改了 `accounts.json` 後同步全掛，或設定被拒絕

**症狀**：啟動或同步直接報錯，其他帳號也停擺。

**原因**：`accounts.json` 內寫了明文 `password`（會被拒絕），或 JSON 格式錯誤（結尾逗號、註解）。

**解法**：
1. 移除明文 `password`，改用 `password_env` 或預設 `TPI_IMAP_PASSWORD_<...>`。
2. 用 `python3 -m json.tool accounts.json` 驗證格式；JSON 不支援註解與結尾逗號。
3. 對照 `accounts.example.json` 的最小結構：`mode` + `accounts[]` + 可選 `calendars`。
4. `accounts.json` 已被 gitignore，不要提交、不要貼到 issue。

**相關檔案**：`accounts.example.json`、`server/features/imap.py`、`.gitignore`、`server/features/providers.py`

---

## T8. Agent 一直 fallback，或摘要永遠是「本機啟發式」

**症狀**：回應帶 `fallback: true`，或文字結尾寫「未接 agent」。

**原因**：`driver` 還是 `local`；或外部驅動失敗（端點不通、模型名稱錯、API key 環境變數沒設、CLI 不在 PATH、回應空白、逾時）。

**解法**：
1. 先把 `driver` 設回 `local` 確認基線功能正常（這是設計上的後備）。
2. `openai_compatible`：確認 `base_url` 指到 OpenAI 相容端點（例如本機 Ollama 的 `/v1`）與 `model` 名稱；API key 由 `api_key_env` 指向的環境變數提供，不要寫進 JSON。
3. `cli`：確認 `command` 每段都在 PATH 上，必要時加大 `timeout_sec`。
4. `http`：worker 必須回 `{"answer": "…"}`。
5. 回應中的 `error` 只給例外類別＋HTTP 狀態碼，細節要在本機端點的日誌看，不要把提示詞或郵件內文貼出去。

**相關檔案**：`agent.example.json`、`server/agent_bridge.py`、`adapters/README.zh-Hant.md`、`server/features/agents.py`

---

## T9. 在 thread 打 `@agent` 沒有反應

**症狀**：送出後回 `triggered: false`，沒有產出成果卡片。

**原因**：（a）訊息裡沒有 `@agent`／`@research`／`@prep`／`@meeting`／`@research-company` 這些路由字；（b）`@` 前面緊貼字母或句點，被邊界規則排除；（c）用 `email_id` 路由既有信件時，收件人不是 agent alias 且內文沒有 `@` 字。

**解法**：
1. 看回應的 `hint`：`no @agent mention` 代表沒觸發到路由字，`not addressed to the agent` 代表這封信既不是寄給 alias、內文也沒有 `@agent`。
2. `@` 前後留空白或標點，例如 `@research Samira Ortiz 最近的往來重點`。
3. 只打 `@agent` 時，會用該 thread 的寄件人（人物研究）或主旨（其他類型）當對象。
4. 記得 alias（`agent@example.com`）只是路由字，**不會有任何信被送出或投遞**。

**相關檔案**：`server/features/agents.py`（`parse_mention`、`MENTION_RE`、`mentions_alias`）、`ui/modules/agents.js`

---

## T10. 成果卡片點開變 404

**症狀**：清單有卡片，但預覽 MD／HTML 失敗。

**原因**：ID 不符合 `^[a-z0-9][a-z0-9-]{2,80}$`、副檔名不是 `md`／`html`／`json`，或檔案已不存在（例如整個 `data/deliverables/` 被清掉）。

**解法**：
1. 從 `GET /api/agents/deliverables?limit=…` 取回**實際**的 `id`，不要自己拼。
2. 確認 `data/deliverables/` 下確實有 `<id>.md`／`.html`／`.json` 三件組。
3. 這是刻意的路徑防護：不合法 ID 一律 404，不會組出任意檔案路徑，所以「猜檔名」不會成功。

**相關檔案**：`server/features/agents.py`（`ID_RE`、`read_deliverable`）、`ui/modules/agents.js`

---

## T11. 搜尋找不到剛同步的信，或刪掉的信還搜得到

**症狀**：關鍵字搜尋結果與收件匣不一致。

**原因**：FTS5 索引落後（同步與索引更新之間有時間差），或本次查詢被查詢解析器條件排除。

**解法**：
1. 先按重新整理讓同步完成，再 `POST /api/search/reindex` 重建索引。
2. 檢查查詢字串有沒有被當成條件（`from:`、`has:attachment`、引號片語、`-` 排除字）。
3. 中文查詢依重疊 bigram 索引；若該臺 Python 的 SQLite 沒有 FTS5，會退回 `LIKE`，結果仍正確但大資料集較慢——慢不等於壞。
4. 刪信後索引由 trigger 同步移除；若仍看到幽靈結果，重建索引後再確認。

**相關檔案**：`server/features/search.py`、`server/features/mailops.py`、`docs/fmb/ARCHITECTURE.md`（5.4）

---

## T12. 技能按了沒反應，或提示被拒絕執行

**症狀**：技能清單有項目，執行後沒有輸出。

**原因**：該技能在設定裡被關掉（存在 `data/skills.json`），關閉的技能會拒絕執行。

**解法**：
1. 用 `POST /api/skills/settings` 把該技能打開。
2. `GET /api/skills` 確認清單與開關狀態。
3. 技能是「先在本機算出結果，有接 BYO agent 時再改寫」；若結果很簡略，先看 T8 確認 agent 狀態，而不是以為技能壞了。
4. 產物位置：投影片在 `data/slides/`、CRM 聯絡人在 `data/contacts.json`（都在 gitignore 的 `data/` 下）。

**相關檔案**：`server/features/skills.py`、`skills/*.md`、`ui/modules/skills.js`

---

## T13. 手機版沒出現、PWA 裝不起來，或 MCP 客戶端連不上

**症狀**：（a）手機開起來還是桌面版；（b）瀏覽器沒有安裝圖示、離線頁沒作用；（c）MCP 客戶端 `initialize` 沒回應。

**原因**：（a）視窗寬度 ≥ 760 px；（b）service worker 只在 HTTPS 或 `127.0.0.1` 生效，且必須透過通道連線；（c）MCP 用 stdio、一行一則 JSON-RPC 訊息，`python3` 路徑或 `OPENINBOX_ROOT` 設錯。

**解法**：
1. 手機版：確認寬度 < 760 px，並用 SSH 埠轉送後開 `http://127.0.0.1:8770/`；`GET /api/mobile/info` 可看實際快取的靜態檔清單（service worker 不碰 `/api/*`，瀏覽器不存信件）。
2. PWA：Chrome／Edge 按側欄「📲 安裝 App」；iOS 用 Safari「加入主畫面」。
3. MCP：先用 README 的一行指令自我測試：

```
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{}}}' '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | python3 server/mcp_server.py
```

   連不上就把 `command` 改成 `python3` 的絕對路徑，並在 `env` 明確設 `OPENINBOX_ROOT` 為 checkout 路徑。MCP 不需要先開網頁面板。

**相關檔案**：`server/mcp_server.py`、`server/features/mobile.py`、`ui/pwa/sw.js`、`README.zh-Hant.md`
