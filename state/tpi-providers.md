# tpi-providers

goal: 多帳號統一收件匣：在既有 gog（Gmail）、gsk（Outlook）driver 之外新增唯讀 IMAP driver（imaplib，帳密只從環境變數或 accounts.json 的 password_env 讀，不寫進檔案），支援 iCloud／其他 IMAP；同步進同一個 inbox 並標帳號；UI 帳號篩選。測試用 mock，不連真信箱。
status: done
next: 等 orchestrator 合併；之後可考慮 IMAP 多 mailbox（mailboxes 清單）與非 ASCII 資料夾名稱（modified UTF-7）

## log
- 2026-10-11 15:20 +08 新增唯讀 IMAP driver `server/features/imap.py`（imaplib；preset icloud／fastmail／yahoo／zoho＋自訂 host；預設 993 SSL＋驗證憑證，starttls 可選，明文只限 loopback；EXAMINE＋BODY.PEEK 不改伺服器狀態；密碼只讀 password_env 或 `TPI_IMAP_PASSWORD_<EMAIL>` 環境變數，accounts.json 放明文 password 直接拒絕，錯誤訊息遮罩密碼）；`yhbmail.py` 只加 `DRIVERS` 登記表與 `LAST_SYNC`（sync_all 依 driver 派送、記每帳號結果）；`server/features/providers.py` 提供 `GET /api/providers`（帳號、驅動、各帳號總數／未讀、憑證狀態只回變數名、上次同步結果、快取中但已不在設定的帳號）與 `POST /api/providers/check`（只登入＋EXAMINE）；`ui/modules/providers.js` 接管側欄帳號篩選（驅動徽章、未讀數、缺密碼／同步錯誤提示、測試連線、`#account=` 深連結），每封信列標帳號標籤，繁中／英文齊全；app.py、index.html 未改；README 雙語補 IMAP 說明。驗證：`python3 -m unittest discover -s tests` 81 OK（新增 30 個 test_tpi_providers_*，用 tests/_tpi_imap_fake.py 本機假 IMAP 伺服器，記錄指令證明無 STORE／EXPUNGE／SELECT）；`scripts/smoke.sh` exit 0；拋棄式副本實起伺服器接兩個假 IMAP 帳號同步，headless Chrome（CDP）確認帳號篩選、語言切換、測試連線 toast、缺密碼提示皆正確。
