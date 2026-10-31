# ADR 0012：PWA service worker 只快取靜態資源

- 狀態：已接受（回溯整理）
- 相關程式：`server/features/mobile.py`（manifest、`/sw.js`、離線頁、圖示、`/api/mobile/info`）、`ui/pwa/sw.js`、`ui/pwa/offline.html`、`ui/modules/mobile.js`

## 背景

使用者希望在 Mac／Windows／iOS／Android 上「像 App 一樣」使用，但不要另外做原生 App。
PWA 可以達成安裝體驗；然而 service worker 一旦快取了 API 回應，信件內容就會留在瀏覽器儲存空間，
這與「本機快取可清除、資料留在自己手上」的承諾衝突（ADR 0006）。

## 決策

1. 提供 manifest（繁中預設、可切英文）、root scope 的 service worker、離線頁與自繪圖示；面板可安裝。
2. **service worker 只處理同源 GET，且只快取靜態資源**：離線頁、manifest、圖示、`ui/modules/*.js`。
3. `/api/*`、任何 POST、跨來源請求**一律不攔截、不快取**。
4. 導覽請求只走網路，失敗才回離線頁（不快取頁面 HTML）。
5. 快取版本以靜態檔內容雜湊決定：任何 UI 或 manifest／圖示變動就換版本，避免使用者卡在舊版。
6. `GET /api/mobile/info` 公開「到底快取了哪些東西」，讓使用者可以自己驗證。
7. 窄螢幕（≤760px）切換行動版版面：底部分頁列、側欄抽屜、全螢幕信件與 Copilot、返回手勢；這些是 UI 行為，與快取策略無關。

## 取捨

**我們放棄**

- 離線可讀信（刻意不做）。
- 推播通知的完整體驗（需要 HTTPS 與授權，目前只做本機輪詢式通知）。

**我們得到**

- 瀏覽器儲存空間裡沒有任何信件；清本機快取仍是唯一需要記得的事。
- 安裝體驗與桌面版共用同一份程式碼。

**已知代價**

- 每次改前端都要想一下版本與快取；改壞了使用者可能看到舊模組。
- service worker 只在 HTTPS 或 `127.0.0.1` 生效，手機要靠通道才進得來（ADR 0001）。

## 後果

- 新增靜態檔時，決定它要不要進預快取；**不要**把任何 API 回應加進 CacheStorage。
- 測試要檢查：CacheStorage 不含 `/` 與 `/api/*`；`/api/*`、POST、跨來源都不被攔截。
- 變更 manifest 或圖示參數時，記得會影響快取版本（已有測試守著）。
