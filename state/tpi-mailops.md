# tpi-mailops

goal: 信件操作：資料夾 Inbox／Starred／Drafts／Sent／Archive／Trash 與封存／刪除／移動／標星（本機狀態）、跨帳號全部標為已讀、列印版頁面（瀏覽器存 PDF）、行內翻譯（BYO agent，無 LLM 清楚提示）、新信通知（Notification API＋/api/new-since 輪詢）、帳號設定（新增／移除／排序主帳號寫 accounts.json）與每帳號簽名＋從檔案匯入。對應 F22 F23 F24 F25 F26 F27。
status: done
next: 等 review／合併；之後若要擴充：資料夾批次多選操作、IMAP 帳號在設定頁顯示憑證狀態（目前在 providers 側欄）

## 實作
- server/features/mailops.py：`mail_state` 表（folder／starred／read 覆蓋，re-sync 不會蓋掉本機已讀）；
  `/api/mailops/folders|list|item|action|empty-trash|mark-all-read`、`/api/new-since`、`/mailops/print`、
  `/api/mailops/translate|languages`、`/api/mailops/accounts[/add|remove|primary|reorder]`、`/api/mailops/signature[/import]`；
  寫入端點拒絕非本機 Origin；accounts.json 原子寫入、拒收明文密碼。
- ui/modules/mailops.js：側欄資料夾＋全部已讀＋通知開關、列表星號、信件動作列（星號／封存／刪除／移動／列印／翻譯）、
  e／s／# 快捷鍵、帳號設定頁（新增／移除／排序／主帳號／簽名／從檔案匯入）、新信撰寫自動附簽名；繁中／英文。
- 未改 server/app.py、ui/index.html（全走 features／ui/modules 外掛）。
- tests：test_tpi_mailops_{folders,read,print,translate,accounts,ui}.py（55 個測試）＋ _tpi_mailops_util.py。

## log
- 2026-10-11 22:47 前一輪：寫好 mailops.py／mailops.js／測試並在 headless Chrome 驗證，但未 commit，檔案隨工作區重置遺失。
- 2026-10-11 23:30 本輪：從前一輪對話紀錄依序重放 28 個寫檔／修改還原全部檔案；修正 folders 測試誤用 srv.request_with_headers（改用 _tpi_mailops_util）；commit。驗證：python3 -m unittest discover -s tests 409 OK（mailops 55 OK）、scripts/smoke.sh OK、headless Chrome CDP 點擊 20 項 UI 檢查＋3 項新信通知檢查全 PASS 無 console 錯誤、/mailops/print 200 含列印 CSS。
- 2026-10-11 23:25 review pass：驗收審查，無需修改程式。驗證：unittest discover 409 OK、scripts/smoke.sh OK；git archive 隔離副本起 server 以 curl 實測 F22 資料夾／標星／封存／刪除／移動／Sent fixture 與跨來源 403、F23 全部已讀（unread 5→0）＋/api/new-since baseline／cursor、F24 /mailops/print 200 含 @media print 與繁中按鈕、F25 無 LLM 回 needs_agent 提示、F26 新增／拒明文密碼 400／主帳號／排序／移除（mode demo↔live 自動切換）寫入 accounts.json、F27 簽名儲存與 .html 匯入轉文字、.exe 拒收；headless Chrome 12 項 UI 檢查（側欄 6 資料夾、動作列、翻譯提示、星號、封存、Starred／Sent、帳號設定頁、繁中字串）＋插入新信後 Notification 觸發全 PASS；硬規則 grep（寄信字樣、部署設定、非 example.com 信箱、非標準庫 import、未動 app.py／index.html／STATE.md）皆無違規。唯一 console 錯誤為核心既有 favicon.ico 404，非本分支。
