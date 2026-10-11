# tpi-calendar

goal: 統一行事曆：週／月檢視、多時區欄、本機建立／編輯事件、RSVP 狀態顯示、agent 工具 create_event（AI 代訂，產 .ics 邀請草稿，不寄出）、匯入同事 ICS（URL 或檔案）並顯示 free/busy 面板。對應 F15 F16 F17。
status: done
next: 第 1 輪審查意見已驗收通過；待 PR #16 第 2 輪 AI 審查／合併 main。給 foundation 的已知 core 小問題（不在本分支範圍）：ui/index.html applyLang 以 textContent 覆寫 nav 按鈕，會吃掉 cnt-* 計數 span，core loadCal 因此在載入模組前拋一次 null 錯誤（無功能影響，calendar.js 已防護）。

## 實作位置
- server/features/calendar.py（路由 /api/cal/*、agent 工具 create_event／find_free_time）、server/features/_ics.py（ICS 解析／RRULE／VTIMEZONE／產生 .ics）
- ui/modules/calendar.js（經 /api/ui-modules 自動載入，接管核心「日曆」檢視；繁中／英文字串）
- fixtures/calendar_demo.json、fixtures/ics/*.ics（虛構，example.com）
- tests/test_tpi_calendar_{view,events,agent,ics,feeds}.py
- 未改 server/app.py、ui/index.html、STATE.md；server/mcp_server.py 只改 mcp_tools 過濾；README 補一句快取說明

## log
- 2026-10-11 20:30 修 create_event 中文標題「討論」+英文主題缺空格（唯一失敗測試）；日曆 fixture／UID 網域改為 example.com 子網域；/api/cal/freebusy 接受 date= 別名並加測試。驗證：python3 -m unittest discover -s tests 250 OK、scripts/smoke.sh OK；暫存副本起 server 實測週／月檢視＋三時區欄、建立／編輯、RSVP（只記本機）、create_event（sent=false、REQUEST .ics）、ICS 檔案匯入與 URL 匯入（需 allow_private 才收本機位址）、free/busy 共同空檔；headless Chrome 截圖確認週／月／空檔／AI 代訂面板正常顯示。
- 2026-10-11 21:22 PR #16 審查第 1 輪：/api/cal/feeds 與 /api/cal/feed/refresh 檢查 Origin（只收無 Origin 或 http://127.0.0.1|localhost:<本機埠>，其餘 403），擋跨站叫本機抓內網；AI 代訂預設說明不再帶原始指令；mcp_tools 只列 TOOL_SPECS 有的工具（create_event／find_free_time 維持 HTTP 專用）；README 中英註明清快取不清 cal_feeds 與刪除方式；新增 tests/test_tpi_calendar_feeds.py（私有位址被拒、本機 HTTP 匯入＋重新整理、重新導向／迴圈、2 MB 上限、跨來源 Origin 含 text/plain 被拒、CLASS:PRIVATE/CONFIDENTIAL 不露標題、不在辦公室／特休整天算忙碌）。驗證：python3 -m unittest discover -s tests 263 OK、scripts/smoke.sh OK；暫存根目錄起 server 用 curl 實測：外來 Origin 新增／重新整理皆 403、本機 Origin 未勾 allow_private 抓 127.0.0.1 仍 502、無 Origin 正常。
- 2026-10-11 21:57 review pass（PR #16 第 1 輪修正驗收）：python3 -m unittest discover -s tests 263 OK（feeds 12 項全過）、scripts/smoke.sh OK；暫存根目錄起 server＋本機 ICS 主機用 curl 實測：外來 Origin（json／text/plain）新增與重新整理、錯埠 Origin 皆 403 且 ICS 主機零命中；本機 Origin 未勾 allow_private 抓 127.0.0.1 為 502、勾了 201 可匯入，無 Origin 重新整理 200；create_event sent=false、.ics DESCRIPTION 只寫「由 AI 代訂」不帶原始指令；清快取後 cal_feeds 保留（與 README 一致）；MCP tools/list 只列 5 個可呼叫工具。順手修小問題：私有位址被擋時錯誤訊息改成指向行事曆的 allow_private 勾選框，不再叫使用者改 agent.json（加測試斷言）。
