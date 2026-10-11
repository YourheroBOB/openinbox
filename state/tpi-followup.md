# tpi-followup

goal: 追蹤與自動化：寄出後 N 天無回覆的 thread 浮上來、JSON 自動化規則（符合條件自動標籤／歸檔／起草本機草稿，先 dry-run）、夜班 agent 腳本 scripts/overnight.py（一次跑完分流＋預備草稿＋早晨交接 brief）。對應 F29 F30 F31。
status: done
next: 交 orchestrator 合併；可選後續：規則加「寄件者網域」快捷欄位、夜班 brief 推到 UI 首頁卡片。

## 功能

- F29 待回覆追蹤：`server/features/followup.py`（`GET /api/followup`、`/api/followup/settings`、`POST /api/followup/state|nudge`），N 天門檻可存（預設 3），完成／延後／重開，追蹤草稿只存本機。
- F30 自動化規則：`server/features/rules.py`（`/api/rules`、`/api/rules/validate`、`/api/rules/run` 預設 dry-run、`/api/rules/runs`、`/api/rules/marks`），動作：label／archive（本機）／mark_read／draft_reply（本機草稿）／task；套用有 ledger 不重做；示範規則 `fixtures/rules_demo.json`，使用者規則 `rules.json`（gitignore）。
- F31 夜班：`server/features/overnight.py` ＋ `scripts/overnight.py`（分流＋規則 dry-run／--apply-rules＋追蹤＋預備草稿＋`data/briefs/` 早晨交接 Markdown/JSON），繁中／英文。
- UI：`ui/modules/followup.js`（三分頁，繁中／英文），經既有 `/api/ui-modules` 自動載入；`server/app.py`、`ui/index.html` 未改。
- 改狀態的 POST 都有同源檢查（`server/features/_origin.py`）。不寄信、不碰遠端信箱。

## log

- 2026-10-11 22:47 第一輪：寫完 followup／rules／overnight／UI 與 4 支測試（工作樹後來遺失，未 commit）。
- 2026-10-11 23:20 從上一輪紀錄復原全部檔案；修測試順序相依（`_tpi_followup_util.Baseline` 先暫存其他套件留下的草稿，避免 m1 已有回覆草稿導致 rules 測試失敗）；驗證：`python3 -m unittest discover -s tests` 389 tests OK、`scripts/smoke.sh` OK、`scripts/overnight.py --root /tmp/fu --no-sync` 繁中／英文 brief 產出且第二次不重複起草、`node --check ui/modules/followup.js` OK。
