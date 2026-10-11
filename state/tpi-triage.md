# tpi-triage

goal: Super Agent 分流視圖：Needs You／Upcoming Today／FYI／Other 四類（由既有五桶映射）、每封信摘要（BYO agent，無 LLM 用 heuristic 並標示）、附件標記、建議後續動作、任務歷史；Other 類產生電子報 digest。API＋UI 模組＋測試。對應 STATE.md F02 F03 F04 F21。
status: done
next: 等 orchestrator 合併；之後可考慮：信件內容變動時讓 agent 摘要失效（目前依 email id＋語言快取）、tpi-followup 可直接沿用 triage_tasks／triage_history 做未回覆追蹤

## log
- 2026-10-11 15:35 +08 新增 `server/features/triage.py`：五桶→四類映射（needs_you→Needs You；upcoming→Upcoming Today＋當天行事曆、`?today=` 可指定；worth_a_look／fyi→FYI 且 worth_a_look 標 high 排前；other→Other；fyi 中明顯電子報移到 Other）；每封信 summary（預設規則式抽取，只照抄原文的期限／金額／日期，標「規則摘要（未接 LLM）／Heuristic summary (no LLM)」；agent.json 設 openai_compatible／cli／http 時 `POST /api/triage/summarize` 走 BYO agent，結果存 agent_turns，所以「清除本機快取」會一起清掉）；附件標記（has_attachment＋內文提到附件／檔名）；建議後續動作（reply／review／read_attachment／rsvp／pay_or_file／unsubscribe／mark_read／follow_up，回覆只開 Copilot 本機草稿）；任務與任務歷史（triage_tasks／triage_history 表，清快取後保留）；Other 類電子報 digest（依寄件者分組、電子報／廣告、Markdown，可選 agent 濃縮）。API：GET /api/triage、/api/triage/item/<id>、/api/triage/digest、/api/triage/tasks、/api/triage/history；POST /api/triage/summarize、/summaries、/digest、/tasks、/tasks/update、/history。`ui/modules/triage.js`：側欄「✦ Super Agent」入口、四類清單（摘要、📎、規則／AI 標籤、待辦數）、詳情面板（摘要、附件、建議動作＋加任務、任務、歷史）、digest 面板、`#view=super` 深連結，郵件列表每列也補摘要與 📎；繁中／英文齊全。app.py、index.html、根目錄 STATE.md 未改。驗證：`python3 -m unittest discover -s tests` 146 OK（新增 65 個 test_tpi_triage_*，BYO agent 用本機 python CLI 假 agent）；`scripts/smoke.sh` exit 0；暫存副本實起 server，headless Chrome（CDP）實點 Super Agent、開信、加任務／完成、digest、重新摘要、起草回覆（Copilot 開啟）、切繁中、深連結、回郵件列表，零 JS 錯誤。
