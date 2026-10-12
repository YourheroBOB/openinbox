# tpi-agents DECISIONS

## Q&A（開工前問題＋預設答案）
| # | 問題（選項） | 預設答案 | 理由 | needs_bob? | BOB 回覆 |
|---|---|---|---|---|---|
| 1 | 研究／會議準備要不要接真實外部搜尋或 LinkedIn／公司資料庫？（A 接外部 B 只用本機信件與 persona＋BYO agent） | B：只用本機快取信件、persona、second brain 與 BYO agent；不連外部資料源 | 外部資料會帶入真實人名與公司，違反硬規則；BYO agent 已可接任何模型 | no | |
| 2 | 「寄到 agent 別名」要不要真的收信？（A 讀 inbound 信件 B 只做 thread 內 @agent） | B：只在 thread 內輸入 `@agent` 觸發；別名以 `agent@example.com` 形式在 fixtures 與設定中佔位，只當路由辨識字串，不做收發 | 不寫寄信／收信程式，且別名不得是真實信箱 | no | |
| 3 | 成果卡片預覽：MD 與 HTML 要同時產生嗎？（A 只 MD B 兩者都產） | B：兩者都產；HTML 經 escape，不含 script，預覽走同源 GET | 符合需求「MD／HTML 可預覽」；HTML 用 escape 降低 XSS 風險 | no | |
| 4 | agent 結果要不要自動存進 Second Brain vault？（A 存 B 只存 deliverable 目錄） | B：只存 `data/deliverables/`（gitignore），不改 vault 卡片 | 避免污染既有 vault 索引；data/ 已被 gitignore | no | |
| 5 | 觸發 agent 是否要二次確認？（A 直接跑 B 先 dry-run 預覽 prompt） | A：直接跑，但 agent 只能讀本機資料、不能寫信；local driver 永遠可用 | 研究是唯讀動作；寫草稿仍走既有 save_draft（本機） | no | |
| 6 | 外部 agent（cli／http／openai_compatible）失敗時怎麼辦？（A 報錯 B 退回本機啟發式並標示） | B：退回 local 並在結果標 `fallback: true` 與 error | 與既有 run_agent 行為一致 | no | |
| 7 | 是否修改 `server/app.py` 與 `ui/index.html`？（A 不改 B 最小掛勾） | 功能走 `server/features/agents.py` 與 `ui/modules/agents.js`；app.py／index.html 不需改動（features 與 ui-modules 已自動載入） | 減少平行分支衝突 | no | |

## 決定
| 日期時間 | 決定 | 採用 | 放棄的選項 | 為什麼 |
|---|---|---|---|---|
| 2026-10-12 09:00 | 新功能模組化 | `server/features/agents.py`、`ui/modules/agents.js`、`tests/test_tpi_agents_*.py` | 改 app.py 加路由 | 依任務簡報，零衝突 |
| 2026-10-12 09:00 | 不新增寄信相關字樣 | 只做草稿（經既有 save_draft 本機）與 deliverable 檔案 | 任何 send 路徑 | 硬規則 |
| 2026-10-12 09:00 | 研究結果寫 `data/deliverables/` | 本機 gitignore 目錄 | vault/cards | 避免污染 vault 索引 |

## 假設（沒問就做的）
### round 1（2026-10-12 09:00）
- 假設：研究與會議準備的 prompt 只餵本機已有資料（fixtures 或 local cache），人名取自 persona/fixtures 的虛構資料。／若錯了影響：可能帶出真實資料。／驗證：測試以 fixtures 驗證 context pack 來源僅限 demo 與本機 DB；grep 硬規則字樣。
- 假設：`@agent` 語法為訊息中出現 `@agent`、`@research`、`@prep` 前綴指令。／若錯了影響：觸發錯誤動作。／驗證：單元測試覆蓋解析。
- 假設：deliverable 檔案名稱只用安全 slug＋時間戳，路徑穿越以 id 白名單擋掉。／驗證：測試 `../` 被拒。

| 2026-10-12 09:20 | 「寄到 agent 別名」只做本機快取路由，不做收信 | `POST /api/agents/mention` 帶 `email_id`，只讀本機快取那封信 | 真正的收信／inbound 連線 | 硬規則：不寫寄收信程式；快取內已有的信可安全路由 |
| 2026-10-12 09:20 | 外部 driver 失敗時退回本機並標記 | fallback=true＋error | 直接回錯誤 | 與既有 run_agent 行為一致，UI 不會空白 |
| 2026-10-12 09:20 | 研究結果同時存 MD、HTML、JSON | `data/deliverables/` | vault/cards | 避免污染 vault 索引（見 Q4） |
| 2026-10-12 09:30 | 發動任務不加二次確認 | 直接跑（唯讀） | dry-run 預覽 | 唯讀動作，寫草稿仍走既有本機 save_draft |
| 2026-10-12 09:30 | 測試用虛構 email 只放 example.com | 測試插入的本機快取列結束後刪除 | 留在共用 DB | 共用測試 DB 不應被測試污染 |

## 假設（沒問就做的）
### round 1（2026-10-12 09:00）
- 假設：研究與會議準備的 prompt 只餵本機已有資料（fixtures 或 local cache），人名取自 persona／fixtures 的虛構資料。／若錯了影響：可能帶出真實資料。／驗證：測試確認 sources 的 id 皆為 `demo:`（本機快取）；grep 硬規則字樣。
- 假設：`@agent` 語法為訊息中出現 `@agent`、`@research`、`@research-company`、`@prep`、`@meeting` 的 token。／若錯了影響：觸發錯誤動作。／驗證：`test_tpi_agents_mention.py` 覆蓋解析與 email 位址不誤判（`name@agent.example.com` 不觸發）。
- 假設：@ 之後整行即為目標（對象），請求動詞（請幫我查、please 等）會被剝掉，單字「查」「研究」僅在後接空白時剝除，以免誤傷「查理」。／若錯了影響：目標含多餘字詞，研究結果稍差，不會寄出任何東西。／驗證：`test_name_starting_with_a_verb_character_is_not_mangled`、`test_polite_words_are_stripped_from_target`。已知限制：`@research Samira Ortiz recent threads` 會把後面的主題也當目標（UI 實測），之後可改成只取前兩個詞。
- 假設：deliverable id 由 kind＋目標 slug＋時間戳組成，之後只用白名單 `^[a-z0-9][a-z0-9-]{2,80}$` 驗證，路徑穿越（`../`、`%2F`）一律 404。／驗證：`test_read_rejects_traversal_and_bad_format`、`test_deliverable_list_and_unknown_id`。
- 假設：HTML 卡片不含 script，UI 以 `sandbox=""` iframe 預覽，不會在本站來源執行任何東西。／驗證：`test_html_card_escapes_and_has_no_script`、`test_html_preview_is_sandboxed_without_scripts`；真瀏覽器實測 iframe sandbox 屬性為空字串。
- 假設：UI 的 `window.setView` 包裝與既有模組相同，不需改 `ui/index.html`。／驗證：真瀏覽器點 nav 進入代理協作、功能正常、無 page error。

## 規則候選（同一錯誤重複才升級成 AGENTS.md／CLAUDE.md 規則）
| 錯誤樣態 | 發生次數 | 最近一次 | 已升級? |
|---|---|---|---|
| UI 把暫態訊息寫進 DOM 後又呼叫會重繪的 renderPane()，訊息被清掉（本輪發生 1 次，已修為存 view 狀態） | 1 | 2026-10-12 09:40 | no |
| 測試把資料寫進共用測試 DB 未清理（本輪寫好後即加 tearDown，發生 0 次實際破壞） | 0 | — | no |
