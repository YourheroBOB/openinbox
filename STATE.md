# STATE — TooPowerInbox（openinbox）

goal: 功能 100% 對齊 Genspark GenMail（BYOK、本機優先、不寄信）
status: doing
next: GB1 orchestrator 依序派工，未完成 WP：tpi-triage、tpi-compose、tpi-skills、tpi-search、tpi-brain、tpi-calendar、tpi-mailops、tpi-outbox、tpi-followup、tpi-agents、tpi-mobile
parity: 4/38（11%）　更新：2026-10-11 15:30 (UTC+8)

## 運作方式
- 正本在 GitHub；GB1 `/workspace/cursor-runs/parity/orchestrate.py` 每 15 分鐘依 work package（WP）派 `run_loop.sh`（最多 4 個平行、分支 `agent/<wp>`、各自狀態檔 `state/<wp>.md`）。
- 每個 WP 完成後由 GB1 PR 自動審查管線（Tier 3）審查，PASS 才 squash 合併；衝突與未完成會自動重派。本檔由 orchestrator 產生，請勿手改。
- 公開 repo 只放通用功能與虛構示範資料；YHB 專屬（客戶名冊分類、真信回填、情報雷達）在私有 repo YourheroBOB/yhb-mail。
- 不部署、不寄信：Schedule／Undo Send 只產生本機 outbox，寄送永遠由使用者自己確認。

## GenMail 功能對照清單（Genspark GenMail 官方說明：https://www.genspark.ai/helpcenter/genmail 、https://www.genspark.ai/genmail 、/tools/ai-email-agent 、/tools/ai-email-assistant（1151011 擷取））

| # | 功能 | 狀態 | WP | 測試 |
|---|---|---|---|---|
| F01 | 統一收件匣：多帳號 Gmail＋Outlook＋其他（IMAP/iCloud）一個 inbox | done | tpi-providers | tests/test_tpi_providers_*.py：gog/gsk/IMAP driver 以假資料 mock 同步進同一 inbox |
| F02 | Super Agent 分流：Needs You／Upcoming Today／FYI／Other 四類（對應既有五桶） | doing | tpi-triage | tests/test_tpi_triage_*.py：demo 信件分到四類、API /api/triage |
| F03 | 每封信 AI 摘要（不開信就懂） | doing | tpi-triage | 單元測試：列表 API 每封帶 summary；無 LLM 時 heuristic |
| F04 | 附件標記＋建議後續動作（回覆／讀附件）＋任務歷史 | doing | tpi-triage | 單元測試：has_attachment、suggested_actions、task history 存取 |
| F05 | 撰寫器：新信／回覆／轉寄（存本機草稿） | doing | tpi-compose | 單元測試＋smoke：/api/compose 三種模式產生草稿 |
| F06 | AI Write：依信件脈絡＋你的語氣起草；調語氣（更正式／更短／更友善）；具體指示 | doing | tpi-compose | 單元測試：tone、instruction 參數影響輸出（local driver） |
| F07 | AI 草稿風格設定 Professional／Balanced／Casual（可逐封覆寫） | doing | tpi-compose | 單元測試：設定存取＋prompt 帶入 |
| F08 | 從你修改草稿中學習語氣（越用越像你） | doing | tpi-compose | 單元測試：草稿 diff 存成 voice sample，persona 更新 |
| F09 | Skills：Morning Brief／Catch Me Up／Organize Inbox／Find It For Me＋可逐項開關 | todo | tpi-skills | 單元測試：四技能可跑、關閉後拒跑 |
| F10 | Skills：Meeting Prep／Brief this person／Turn into a slide／CRM this contact | todo | tpi-skills | 單元測試：四技能輸出（slide=HTML/MD 檔、CRM=本機 contacts.json） |
| F11 | 自然語言搜尋（依語意找信，含 from／日期／附件條件） | todo | tpi-search | 單元測試：FTS5＋NL 查詢解析，demo 資料命中 |
| F12 | 聯絡人搜尋與聯絡人清單 | todo | tpi-search | 單元測試：/api/contacts 與搜尋 |
| F13 | Email Brain 分頁：身分職場、寫作語氣、常聯絡人與關係、進行中專案、工作模式 | todo | tpi-brain | 單元測試：/api/brain/profile 各區塊由 demo 信件推得 |
| F14 | Email Brain「Fix」修正推論，立即影響後續行為 | todo | tpi-brain | 單元測試：fix 後 profile 與 draft prompt 反映修正 |
| F15 | 統一行事曆：週／月檢視、多時區、建立事件、RSVP 狀態 | todo | tpi-calendar | 單元測試＋smoke：事件 CRUD（本機）、時區轉換、RSVP 欄位 |
| F16 | AI 代訂會議（agent 可建立事件）＋邀請草稿 | todo | tpi-calendar | 單元測試：agent tool create_event＋產 .ics 邀請草稿（不寄出） |
| F17 | 同事行事曆分享檢視＋free/busy 面板 | todo | tpi-calendar | 單元測試：匯入 ICS URL/檔案、free/busy 計算 |
| F18 | Schedule Send＋Scheduled 資料夾（可編輯／取消） | todo | tpi-outbox | 單元測試：排程佇列、取消、到期移到 outbox（本機，無寄信傳輸） |
| F19 | Undo Send 倒數（倒數內可取消） | todo | tpi-outbox | 單元測試＋UI：倒數取消流程 |
| F20 | 寄出前一律人工確認（agent 不代你發言） | todo | tpi-outbox | 單元測試：未確認的草稿不得進 outbox；預設無寄信傳輸 |
| F21 | 電子報／廣告整理成 digest | doing | tpi-triage | 單元測試：Other 類生成 digest |
| F22 | 資料夾與動作：Inbox／Starred／Drafts／Sent／Archive／Trash；封存／刪除／移動／標星 | todo | tpi-mailops | 單元測試：本機狀態切換＋API |
| F23 | 全部標為已讀（跨所有帳號） | todo | tpi-mailops | 單元測試：/api/mark-all-read |
| F24 | 預覽／列印／存成 PDF | todo | tpi-mailops | smoke：/print/<id> 印刷版 HTML（瀏覽器存 PDF） |
| F25 | 一鍵行內翻譯（讀與回覆） | todo | tpi-mailops | 單元測試：/api/translate（BYO agent；無 LLM 時清楚提示） |
| F26 | 新信通知（桌面／手機） | todo | tpi-mailops | UI：Notification API＋輪詢；單元測試 /api/new-since |
| F27 | 帳號設定：新增／移除／排序主帳號；每帳號簽名＋匯入 | todo | tpi-mailops | 單元測試：accounts API 寫 accounts.json、signature 存取 |
| F28 | 撰寫器中日韓字型選擇 | doing | tpi-compose | UI＋單元測試：字型設定存取 |
| F29 | 追蹤未回覆（寄出後沒回的 thread 浮上來） | todo | tpi-followup | 單元測試：N 天無回覆偵測 |
| F30 | 自動化規則：符合條件的信自動標籤／歸檔／起草 | todo | tpi-followup | 單元測試：JSON 規則 dry-run 與套用 |
| F31 | 夜班 agent：背景分流＋預備草稿＋早晨交接 | todo | tpi-followup | 單元測試：scripts/overnight 一次跑完產出 brief |
| F32 | Super agent 動作：研究人物／公司、會議準備（BYO agent＋連接器） | todo | tpi-agents | 單元測試：research/meeting-prep 經 agent bridge |
| F33 | GenTeam：寄信／@ 提及 agent 進 thread、成果卡片預覽 | todo | tpi-agents | 單元測試：@agent 觸發、deliverable card API |
| F34 | Agent 連接器：MCP 伺服器（stdio JSON-RPC）提供 inbox 工具 | done | tpi-mcp | 單元測試：initialize／tools/list／tools/call |
| F35 | 用量／點數頁 → BYOK token 用量紀錄 | todo | tpi-skills | 單元測試：usage jsonl 記錄與 /api/usage |
| F36 | Mac／Windows／iOS／Android → 可安裝 PWA＋行動版版面 | todo | tpi-mobile | smoke：manifest、service worker、窄螢幕版面 |
| F37 | 隱私：信件留在信箱供應商；本機快取可清除；不經第三方伺服器 | done | tpi-foundation | README 說明＋單元測試：/api/cache/clear |
| F38 | Linux／雲端主機可跑（tests＋smoke 綠燈、雲端執行說明） | done | tpi-foundation | scripts/smoke.sh＋CI unittest 綠燈 |

## 既有功能（10/10 版本已具備）
- 三欄 inbox UI、五桶分流、鍵盤操作、已讀／未讀、深連結（smoke.yml）
- Copilot 抽屜：30 秒摘要、待辦／期限、三版回覆草稿存本機（/api/copilot）
- Second Brain 卡片、Know-you-better persona、BYO agent（local／OpenAI 相容／CLI／HTTP）、/api/v1 工具 API
- 繁中／英文介面；送信預設關閉

## WP 狀態
| WP | 狀態 | 依賴 | 嘗試 | PR |
|---|---|---|---|---|
| tpi-foundation | merged | - | 1 | https://github.com/YourheroBOB/openinbox/pull/2 |
| tpi-mcp | merged | - | 2 | https://github.com/YourheroBOB/openinbox/pull/3 |
| tpi-providers | merged | tpi-foundation | 2 | https://github.com/YourheroBOB/openinbox/pull/6 |
| tpi-triage | running | tpi-foundation | 3 | - |
| tpi-compose | running | tpi-foundation | 1 | - |
| tpi-skills | pending | tpi-foundation | 0 | - |
| tpi-search | pending | tpi-foundation | 0 | - |
| tpi-brain | pending | tpi-foundation | 0 | - |
| tpi-calendar | pending | tpi-foundation | 0 | - |
| tpi-mailops | pending | tpi-foundation | 0 | - |
| tpi-outbox | pending | tpi-compose | 0 | - |
| tpi-followup | pending | tpi-triage | 0 | - |
| tpi-agents | pending | tpi-skills | 0 | - |
| tpi-mobile | pending | tpi-mailops | 0 | - |

## 來源卡片
- Linear HQ-1173：土炮 GenMail MVP（openinbox＋gsk 驅動＋BYOK，本機 8788 埠）。
- Linear HQ-1299：v2.0（分類器升級、歷史回填、情報雷達、MCP 伺服器）— YHB 專屬部分已移到私有 yhb-mail；通用 MCP 伺服器在本 repo 由 tpi-mcp 實作。

## log
- [2026-10-11 14:00:57] STATE sync PR https://github.com/YourheroBOB/openinbox/pull/4
- [2026-10-11 14:18:03] defer launch: GB1 MemAvailable 0.6G < 3.5G
- [2026-10-11 14:30:03] launch tpi-mcp attempt 2 (conflict) log=/workspace/cursor-runs/tpi-mcp-conflict2.log
- [2026-10-11 14:30:09] launch tpi-providers attempt 1 (a) log=/workspace/cursor-runs/tpi-providers-a1.log
- [2026-10-11 14:30:10] launch tpi-triage attempt 1 (a) log=/workspace/cursor-runs/tpi-triage-a1.log
- [2026-10-11 14:30:10] defer launch: GB1 已有 3 個 run_loop（上限 3）
- [2026-10-11 14:45:13] tpi-mcp remote test auto 8c1b950: pass
- [2026-10-11 14:45:18] launch tpi-providers attempt 2 (r) log=/workspace/cursor-runs/tpi-providers-r2.log
- [2026-10-11 14:45:18] defer launch: GB1 已有 3 個 run_loop（上限 3）
- [2026-10-11 14:45:18] defer launch: GB1 已有 3 個 run_loop（上限 3）
- [2026-10-11 15:00:03] tpi-mcp merged https://github.com/YourheroBOB/openinbox/pull/3
- [2026-10-11 15:00:25] tpi-providers remote test auto 06d7b66: pass
- [2026-10-11 15:00:30] launch tpi-triage attempt 2 (r) log=/workspace/cursor-runs/tpi-triage-r2.log
- [2026-10-11 15:00:30] defer launch: GB1 已有 3 個 run_loop（上限 3）
- [2026-10-11 15:00:33] STATE sync PR https://github.com/YourheroBOB/openinbox/pull/5
- [2026-10-11 15:15:02] tpi-providers merged https://github.com/YourheroBOB/openinbox/pull/6
- [2026-10-11 15:15:07] launch tpi-triage attempt 3 (r) log=/workspace/cursor-runs/tpi-triage-r3.log
- [2026-10-11 15:15:07] defer launch: GB1 已有 3 個 run_loop（上限 3）
- [2026-10-11 15:30:08] launch tpi-compose attempt 1 (a) log=/workspace/cursor-runs/tpi-compose-a1.log
- [2026-10-11 15:30:08] defer launch: GB1 已有 3 個 run_loop（上限 3）
