# 使用者常見問題（U1–U12）

適用對象：在自己機器或雲端主機上跑 TooPowerInbox、但不打算改程式碼的人。
以下行為以 `README.md`／`README.zh-Hant.md` 與 `server/` 目前程式為準。

---

## U1. 第一次啟動要做什麼？

**問題**：clone 之後不知道怎麼跑起來，也不知道會不會動到我的設定。

**原因**：專案需要先建立本機資料夾與預設設定檔，`run.sh` 只是啟動器。

**解法**：
1. 在 repo 根目錄執行 `./install.sh`，再執行 `./run.sh`。
2. 瀏覽器開 `http://127.0.0.1:8770/`，第一次開機會載入示範信件。
3. `install.sh` 只做三件事：檢查 Python 3.9 以上、建立 `data/` 與 `vault/cards/`、在檔案**不存在**時複製 `accounts.example.json → accounts.json`、`agent.example.json → agent.json`。它不會覆寫你既有的設定檔。
4. 想改埠號用 `OPENINBOX_PORT=8771 ./run.sh`；不想自動開瀏覽器用 `OPENINBOX_NO_BROWSER=1 ./run.sh`。

**相關檔案**：`install.sh`、`run.sh`、`accounts.example.json`、`agent.example.json`、`README.zh-Hant.md`

---

## U2. 沒有任何信箱帳號，可以玩嗎？

**問題**：不想把真信箱接進來，但想先看功能。

**原因**：預設就是示範模式，資料來自 `fixtures/` 的虛構信件與行事曆。

**解法**：直接 `./run.sh` 即可，不需要登入。想回到乾淨的示範狀態，用側欄「清除本機快取」或 `POST /api/cache/clear`，body 帶 `{"reseed": true}` 會重新載入示範資料。`GET /api/cache` 可以看目前快取了什麼。

**相關檔案**：`fixtures/demo_inbox.json`、`fixtures/calendar_demo.json`、`server/features/cache.py`、`server/yhbmail.py`

---

## U3. 怎麼切換繁體中文／英文？

**問題**：介面是英文（或中文），想換語言。

**原因**：面板同時提供 `zh-Hant` 與 `en` 兩套字串。

**解法**：按左側的「繁中／EN」，或在網址加上 `?lang=zh-Hant` / `?lang=en`。深連結（例如 `#thread=…`、`#view=agents`）可以和語系參數一起用。

**相關檔案**：`ui/index.html`、`ui/modules/*.js`、`README.zh-Hant.md`

---

## U4. 要怎麼接真信箱？為什麼一直停在示範信？

**問題**：改了 `accounts.json`，收件匣還是示範資料。

**原因**：`mode` 還是 `demo`，或帳號驅動（driver）沒填對，或還沒觸發同步。

**解法**：
1. 把 `accounts.json` 的 `mode` 改成 `"live"`，並在 `accounts` 列出帳號。
2. 驅動可選：`gog`（Gmail，走 gog CLI）、`gsk`（額外 IMAP／Outlook，只當郵件傳輸）、`imap`（唯讀 IMAP）。
3. 存檔後在面板按「重新整理」觸發同步；若帳號清單沒更新，重啟 `./run.sh` 讓設定重新載入。
4. 用 `GET /api/providers` 確認每個帳號的信件數、未讀數、上次同步結果；IMAP 帳號可用「測試連線」（`POST /api/providers/check`）。

**相關檔案**：`accounts.example.json`、`server/features/providers.py`、`server/features/imap.py`、`server/yhbmail.py`

---

## U5. IMAP 的密碼要放哪裡？為什麼一直顯示「缺密碼」？

**問題**：iCloud／Fastmail 等帳號同步不了，側欄提示缺少密碼。

**原因**：程式只從**環境變數**讀密碼，不從 `accounts.json` 讀明文；變數名稱必須對得上。

**解法**：
1. 在 `accounts.json` 的帳號寫 `"password_env": "TPI_IMAP_ICLOUD_PASSWORD"`，或省略讓程式用預設命名：`TPI_IMAP_PASSWORD_<信箱大寫、非英數換成 _>`（例：`me@example.com` → `TPI_IMAP_PASSWORD_ME_EXAMPLE_COM`）。
2. 在啟動伺服器的同一個 shell `export` 該變數，再 `./run.sh`。不要寫進任何檔案、也不要 commit。
3. iCloud 要用 Apple ID 的 **App 專用密碼**，不是登入密碼。
4. `accounts.json` 裡放明文 `"password"` 會被直接拒絕，這是刻意的。

**相關檔案**：`server/features/imap.py`、`server/features/providers.py`、`adapters/README.zh-Hant.md`、`README.zh-Hant.md`

---

## U6. IMAP 同步會不會把信標成已讀、或動到伺服器上的信？

**問題**：擔心同步後信箱狀態被改。

**原因**：這是唯讀設計，不是一般 IMAP 客戶端。

**解法**：不需要調整。IMAP 以 `EXAMINE` 開信箱、`BODY.PEEK` 抓信，不設定已讀旗標、不刪除、不移動；「測試連線」（`POST /api/providers/check`）也只做登入＋`EXAMINE`。想確認實際下過的指令，可看 `tests/_tpi_imap_fake.py` 這類本機假伺服器的測試斷言。

**相關檔案**：`server/features/imap.py`、`server/features/providers.py`、`tests/_tpi_imap_fake.py`、`docs/fmb/ARCHITECTURE.md`

---

## U7. Copilot／摘要看起來很陽春，還寫「未接 LLM」？

**問題**：摘要、待辦萃取、回信草稿只有規則式結果。

**原因**：`agent.json` 的 `driver` 是 `local`，或外部 Agent 呼叫失敗後退回本機啟發式（回應會標 `fallback`）。

**解法**：
1. 這是預期行為，不是 bug：沒有 BYO Agent 時一定會降級，而且會明確標示。
2. 要更好的結果，把 `agent.json` 改成 `openai_compatible`（OpenAI、Ollama、vLLM、LiteLLM）、`cli`（吃 stdin 的 Agent）或 `http`（你自己的 worker）。
3. API key 用 `api_key_env` 指向環境變數，不要寫死在 JSON。
4. 失敗時回應中的 `error` 只會是例外類別＋HTTP 狀態碼，不會帶端點回應內文或提示詞。

**相關檔案**：`agent.example.json`、`server/agent_bridge.py`、`adapters/README.zh-Hant.md`、`server/features/agents.py`（`error_label`）

---

## U8. 草稿會不會不小心被寄出去？

**問題**：想確認系統不會代替我發信。

**原因**：專案的產品契約是「不預設寄信」。

**解法**：不會寄出。草稿只寫本機 SQLite；排程到期的項目只是移進本機 outbox；寄出前需要人工確認（確認 token／`ack`），倒數期間可取消，取消不會刪掉原始草稿。MCP 的 `save_draft` 也只寫本機草稿表。整個 repo 沒有啟用中的對外寄送路徑。

**相關檔案**：`server/features/outbox.py`、`server/features/_outbox_transport.py`、`server/mcp_server.py`、`docs/fmb/ARCHITECTURE.md`

---

## U9. 「清除本機快取」到底會刪掉什麼？

**問題**：怕按下去把重要資料清光。

**原因**：這是資料隔離操作（給示範資料或換機器用），不是備份或還原機制。

**解法**：會被清掉的是郵件快取、示範／快取行事曆、Agent 回合結果（`agent_turns`）、衍生卡片，以及衍生的人格與搜尋索引。**會保留**草稿、你自己寫的筆記卡、本機建立或匯入的行事曆資料、邀請草稿與匯入的同事 ICS feed（`cal_feeds`）。要重載示範信就帶 `{"reseed": true}`。

**相關檔案**：`server/features/cache.py`、`ui/modules/cache.js`、`docs/fmb/ARCHITECTURE.md`（5.9）

---

## U10. 該備份哪些檔案？可以直接複製 `data/` 嗎？

**問題**：想備份郵件快取、人格、卡片、草稿與設定。

**原因**：目前**沒有內建備份／還原流程**，這件事在 `docs/fmb/ROADMAP.md` 是 P0 缺口。

**解法**：
1. 需要備份的是 `data/`、`vault/`，以及 `accounts.json`、`agent.json`、`rules.json`（後三者屬設定，含帳號中繼資料，權限要收紧）。
2. 不要直接複製**執行中**的 SQLite 檔，可能拿到不一致的內容；請先停掉 `run.sh` 再快照，或用 SQLite 的備份機制。
3. 備份內容不要含任何憑證值（密碼本來就只在環境變數）。
4. 這台機器上的 `data/`、`vault/` 等於你的信箱，磁碟權限要當信箱等級保護。

**相關檔案**：`docs/fmb/ROADMAP.md`（第 1 項）、`.gitignore`、`docs/fmb/ARCHITECTURE.md`（4.2）

---

## U11. 怎麼裝成 App？手機上怎麼用？

**問題**：想從桌面／手機主畫面直接開。

**原因**：TooPowerInbox 是可安裝的 PWA，沒有另外的原生 App。

**解法**：
1. Chrome／Edge（Mac、Windows、Linux、Android）：開 `http://127.0.0.1:8770/`，按側欄「📲 安裝 App」或網址列的安裝圖示。
2. iPhone／iPad：Safari → 分享 → 加入主畫面。
3. Service worker 只在 HTTPS 或 `127.0.0.1` 生效，所以手機要先做 SSH 連線埠轉送，再開 `http://127.0.0.1:8770/`；伺服器仍然只聽本機。
4. 寬度小於 760 px 會切成手機版（底部分頁列、側欄抽屜、全螢幕信件）。`GET /api/mobile/info` 可看實際快取了哪些靜態檔。

**相關檔案**：`server/features/mobile.py`、`ui/pwa/sw.js`、`ui/pwa/offline.html`、`ui/modules/mobile.js`

---

## U12. 可以放在雲端 Linux 主機上跑嗎？

**問題**：想讓它常駐在遠端主機，但不想開對外埠。

**原因**：伺服器只綁 `127.0.0.1:8770`，不支援公開部署。

**解法**：
1. 主機上：`git clone … && cd openinbox && ./install.sh`，再 `OPENINBOX_NO_BROWSER=1 ./run.sh`（可放 tmux／screen）。
2. 筆電上：`ssh -N -L 8770:127.0.0.1:8770 user@your-host.example.com`，然後開 `http://127.0.0.1:8770/`。
3. 本機 8770 被占用就改成 `-L 8771:127.0.0.1:8770` 開 8771。
4. 主機防火牆**不要**放行 8770；通道是唯一入口。不要把 `0.0.0.0` 綁定當成受支援情境。

**相關檔案**：`README.zh-Hant.md`（在雲端 Linux 主機執行）、`run.sh`、`server/app.py`
