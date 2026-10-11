# tpi-foundation

goal: openinbox 基礎建設：(1) 建 tests/（只用標準函式庫 unittest），涵蓋既有 API（health、inbox、copilot、agent/run、drafts）；(2) scripts/smoke.sh 在 Linux 起伺服器跑與 .github/workflows/smoke.yml 相同
status: done
next: 等 orchestrator 合併；之後新功能一律放 server/features/<name>.py + ui/modules/<name>.js + tests/test_tpi_foundation_<name>.py

## log
- 2026-10-11 13:55 +08 建 server/features 外掛機制（app.py 只加 import + `Handler = features.mount(Handler)`；plugins.py 提供 /api/features、/api/ui-modules、/ui/modules/*）；index.html 加單一 loader；ui/modules/cache.js 側欄「清除本機快取／Clear local cache」；features/cache.py 提供 GET /api/cache、POST /api/cache/clear（清信件／行程／agent_turns／衍生卡片，保留草稿與筆記卡，可 reseed）；tests/ 51 個 unittest（API、外掛、快取、repo 規則）；scripts/smoke.sh 直接解析 smoke.yml 的 run 步驟在拋棄式副本執行；smoke.yml 加 unittest 步驟；README 雙語加「在雲端 Linux 主機執行」（ssh -L）、加功能、測試；修 agent_bridge 缺 ACTION_RE import（Copilot todos 模式原本會斷線）。驗證：`python3 -m unittest discover -s tests` 51 OK；`scripts/smoke.sh` exit 0（含 8770 被占用時自動換埠）；headless Chrome 確認 loader 注入按鈕。
