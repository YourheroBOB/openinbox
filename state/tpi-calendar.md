# tpi-calendar

goal: 統一行事曆：週／月檢視、多時區欄、本機建立／編輯事件、RSVP 狀態顯示、agent 工具 create_event（AI 代訂，產 .ics 邀請草稿，不寄出）、匯入同事 ICS（URL 或檔案）並顯示 free/busy 面板。對應 F15 F16 F17。
status: done
next: 待合併 main。給 foundation 的已知 core 小問題（不在本分支範圍）：ui/index.html applyLang 以 textContent 覆寫 nav 按鈕，會吃掉 cnt-* 計數 span，core loadCal 因此在載入模組前拋一次 null 錯誤（無功能影響，calendar.js 已防護）。

## 實作位置
- server/features/calendar.py（路由 /api/cal/*、agent 工具 create_event／find_free_time）、server/features/_ics.py（ICS 解析／RRULE／VTIMEZONE／產生 .ics）
- ui/modules/calendar.js（經 /api/ui-modules 自動載入，接管核心「日曆」檢視；繁中／英文字串）
- fixtures/calendar_demo.json、fixtures/ics/*.ics（虛構，example.com）
- tests/test_tpi_calendar_{view,events,agent,ics}.py
- 未改 server/app.py、ui/index.html、STATE.md

## log
- 2026-10-11 20:30 修 create_event 中文標題「討論」+英文主題缺空格（唯一失敗測試）；日曆 fixture／UID 網域改為 example.com 子網域；/api/cal/freebusy 接受 date= 別名並加測試。驗證：python3 -m unittest discover -s tests 250 OK、scripts/smoke.sh OK；暫存副本起 server 實測週／月檢視＋三時區欄、建立／編輯、RSVP（只記本機）、create_event（sent=false、REQUEST .ics）、ICS 檔案匯入與 URL 匯入（需 allow_private 才收本機位址）、free/busy 共同空檔；headless Chrome 截圖確認週／月／空檔／AI 代訂面板正常顯示。
