# tpi-mobile

goal: 可安裝 PWA：manifest、service worker（只快取靜態資源）、窄螢幕行動版版面，取代原生 Mac／Windows／iOS／Android app。對應 F36。
status: done
next: 等 review／合併；之後若要擴充：推播通知（需 HTTPS＋使用者授權，目前不做）、手機版下拉重新整理、iOS 啟動畫面（apple-touch-startup-image）

## 實作
- server/features/mobile.py：`/manifest.webmanifest`（繁中預設、`?lang=en` 英文；id/start_url/scope 皆 `/`、standalone、主畫面捷徑：郵件／日曆／草稿／Copilot）、
  `/sw.js`（root scope，版本＝靜態檔 sha256 前 12 碼，任何 UI 檔變動即換快取）、`/offline.html`、
  圖示（純標準庫 zlib 畫 PNG：192／512 any＋maskable、180 apple-touch-icon、48 favicon；另有 SVG）、`/api/mobile/info`（列出確切快取清單）。
- ui/pwa/sw.js：只處理同源 GET；`/api/*`、POST、跨來源一律不攔截；導覽只走網路、失敗才回離線頁（不快取頁面 HTML）；
  離線頁／manifest／圖示 cache-first（預先快取）；`ui/modules/*.js` network-first（離線才用快取）；activate 清掉舊版 `tpi-static-*`。
- ui/pwa/offline.html：繁中／英文離線頁（重試按鈕、online 事件自動重試，不載外部資源）。
- ui/modules/mobile.js：註冊 SW、「📲 安裝 App」按鈕（beforeinstallprompt；iOS 顯示「分享→加入主畫面」說明）、
  ≤760px 手機版：底部分頁列（郵件／日曆／草稿／Copilot／選單）、側欄滑出抽屜、信件與 Copilot 全螢幕、返回鍵／手勢（history 堆疊）關閉、
  撰寫器全螢幕、日曆週檢視可橫向捲動、safe-area；伺服器連不到時顯示離線橫幅；切換語言同步換 manifest。
- ui/index.html 最小掛勾：<head> 加 manifest／theme-color／apple meta／icon 連結、viewport-fit=cover、一行提早攔截 beforeinstallprompt。未改 server/app.py、STATE.md。
- README（英／繁中）新增「安裝成 App」一節與目錄列。
- tests：test_tpi_mobile_{manifest,icons,sw,ui}.py（42 個測試）＋ _tpi_mobile_cdp.js（Node 22+ 驅動 headless Chrome；無 Chrome 或 Node<22 自動 skip）。

## log
- 2026-10-12 00:16 本輪：從零實作 F36 全部（上列檔案）並 commit。驗證：python3 -m unittest discover -s tests 491 OK（mobile 42 OK、無 skip）、scripts/smoke.sh OK；
  Node vm 內實跑 sw.js（假 caches/fetch）證明 /api/*、POST、跨來源、/mailops/print 皆不攔截且快取只含靜態路徑；
  headless Chrome CDP 390×844：Page.getInstallabilityErrors 為空、SW 控制頁面、CacheStorage 無 /api/ 與 /、抽屜／信件詳情／返回鍵／Copilot／撰寫器全螢幕／語言切換／1280 寬桌面版不變，皆無頁面例外；
  另起一支拋棄式伺服器後砍掉：開啟中顯示離線橫幅、重新導覽由 SW 回離線頁；截圖人工檢視版面；硬規則 grep（寄信字樣、非 example 信箱、部署檔、workflow 字樣）皆無。
