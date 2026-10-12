# tpi-followup

goal: 追蹤與自動化：寄出後 N 天無回覆的 thread 浮上來、JSON 自動化規則（符合條件自動標籤／歸檔／起草本機草稿，先 dry-run）、夜班 agent 腳本 scripts/overnight.py（一次跑完分流＋預備草稿＋早晨交接 brief）。對應 F29 F30 F31。
status: done
next: 第 1 輪審查修正已驗收通過，交 orchestrator 進 PR #20 第 2 輪 AI 審查／合併；可選後續：規則加「寄件者網域」快捷欄位、夜班 brief 推到 UI 首頁卡片。

## 功能

- F29 待回覆追蹤：`server/features/followup.py`（`GET /api/followup`、`/api/followup/settings`、`POST /api/followup/state|nudge`），N 天門檻可存（預設 3），完成／延後／重開，追蹤草稿只存本機。
- F30 自動化規則：`server/features/rules.py`（`/api/rules`、`/api/rules/validate`、`/api/rules/run` 預設 dry-run、`/api/rules/runs`、`/api/rules/marks`），動作：label／archive（本機）／mark_read／draft_reply（本機草稿）／task；套用有 ledger 不重做；示範規則 `fixtures/rules_demo.json`，使用者規則 `rules.json`（gitignore）。
- F31 夜班：`server/features/overnight.py` ＋ `scripts/overnight.py`（分流＋規則 dry-run／--apply-rules＋追蹤＋預備草稿＋`data/briefs/` 早晨交接 Markdown/JSON），繁中／英文。
- UI：`ui/modules/followup.js`（三分頁，繁中／英文），經既有 `/api/ui-modules` 自動載入；`server/app.py`、`ui/index.html` 未改。
- 改狀態的 POST 都有同源檢查（`server/features/_origin.py`）。不寄信、不碰遠端信箱。

## log

- 2026-10-11 22:47 第一輪：寫完 followup／rules／overnight／UI 與 4 支測試（工作樹後來遺失，未 commit）。
- 2026-10-11 23:20 從上一輪紀錄復原全部檔案；修測試順序相依（`_tpi_followup_util.Baseline` 先暫存其他套件留下的草稿，避免 m1 已有回覆草稿導致 rules 測試失敗）；驗證：`python3 -m unittest discover -s tests` 389 tests OK、`scripts/smoke.sh` OK、`scripts/overnight.py --root /tmp/fu --no-sync` 繁中／英文 brief 產出且第二次不重複起草、`node --check ui/modules/followup.js` OK。
- 2026-10-11 23:22 review pass：實測三功能可用。修一個小 bug：`scripts/overnight.py --root <空目錄>` 因 demo fixture 路徑跟著 root 走而崩潰（FileNotFoundError），改為 root 無 fixture 時退回 repo `fixtures/`，並補 `test_script_on_an_empty_root_uses_repo_fixtures`（修前失敗、修後通過）。驗證：`python3 -m unittest discover -s tests` 390 tests OK、`scripts/smoke.sh` OK；空 root 跑夜班繁中／英文 brief、`--apply-rules` 套用 6 個動作且再跑為 0；起伺服器以 HTTP 實測 `/api/followup`（N 天門檻改 7 天即時生效、done、nudge 本機草稿）、`/api/rules/run` 預設 dry-run、`/api/rules/validate` 擋未知動作 `send`、5 支 POST 跨來源皆 403；禁用字／部署檔／workflow 字樣掃描乾淨，`server/app.py`、`ui/index.html`、`STATE.md` 未改。
- 2026-10-11 23:50 PR #20 審查第 1 輪修正：`rules.run()` 在 dry_run=false 且 rules.json 有錯時回 400、一條都不套用（夜班照樣出 brief，錯誤列進 errors、套用 0）；`validate()` 規則只要有任何 id／條件／動作錯誤就整條排除；`matches()` 條件為空一律 False；補 4 支測試（手寫欄位打錯的 rules.json 跑 `/api/rules/run` dry_run=false 與 `scripts/overnight.py --apply-rules` 皆 0 動作、標記／已讀／草稿／任務／rule_runs 都沒變）。驗證：還原修正時新測試 5 項失敗、修正後通過；`python3 -m unittest discover -s tests` 394 tests OK、`scripts/smoke.sh` OK。
- 2026-10-11 23:43 review pass（PR #20 第 1 輪修正驗收）：四項要求逐一實測可用。在 repo 暫存副本放自寫的打錯 rules.json（`feild` 拼錯、any 規則一好一壞條件、一好一壞動作、空 conditions），`scripts/overnight.py --no-sync --apply-rules --json` exit 1、套用／符合 0、rule_marks／rule_applied／rule_runs 皆 0、未讀數不變、brief 照出；起伺服器以 HTTP 實測 `/api/rules/run` dry_run=false 回 400（繁中／英文）、dry-run 0 條規則、`/api/rules` 四條全被排除、`/api/rules/runs` 空；把 rules.json 修好後套用 5 個動作、再跑 0（already 5），跨來源 403。小修：夜班 brief／`--json` 的規則錯誤前加上規則 id（原本看不出哪條要修），測試補斷言（修前失敗、修後通過）。驗證：`python3 -m unittest discover -s tests` 394 tests OK、`scripts/smoke.sh` OK。
