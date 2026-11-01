# ADR-0010：PWA 可安裝但永不快取 `/api/*`

- 狀態：已接受（現況仍有效）
- 日期：事後補建（原始決策日未記錄）
- 影響範圍：`server/features/mobile.py`、`ui/pwa/`、README 安裝章節
- 相關：ADR-0007、ADR-0008

## 背景

產品希望「可安裝、像 App」，但郵件內容是最高敏感資料。Service worker 一旦快取了 API 回應，
內容就會留在瀏覽器儲存裡，脫離使用者的掌握，也違反「郵件不離開本機」的敘事。

## 決策

1. Service worker（`/sw.js`，由 `mobile.py` 提供）**只快取靜態檔**：離線頁、manifest、
   圖示、`ui/modules/*.js`。
2. **絕不碰 `/api/*`**：任何郵件、草稿、行事曆、人格資料都不進瀏覽器儲存。
3. 連不到伺服器時顯示靜態離線頁與「重試」按鈕，不顯示先前內容。
4. `GET /api/mobile/info` 明確列出目前快取了哪些東西，可驗證、可稽核。
5. 手機流程靠 SSH App 轉送連接埠（`ssh -N -L 8770:127.0.0.1:8770`），伺服器仍只聽 loopback
   （ADR-0007）；SW 只在 HTTPS 或 `127.0.0.1` 等安全內容環境運作。
6. 窄屏（<760 px）切手機版：底部分頁列、側欄抽展、全螢幕訊息與 Copilot、主畫面捷徑。

## 取捨

| 考慮過的做法 | 為什麼沒有選 |
|---|---|
| 快取 API 回應做離線閱讀 | 郵件進瀏覽器儲存，違反隱私邊界 |
| 開發原生 App | 維護成本與發版流程與單機定位不合 |
| 不做 PWA | 「可安裝」是明確的使用者價值，成本卻很低 |

## 後果

**正面**

- 可安裝、有離線殼，但離線時看不到任何郵件——邊界可對外說明。
- `/api/mobile/info` 讓快取內容可稽核，不會悄悄變大。

**負面／代價**

- 離線功能僅限「殼」，真正離線閱讀不在範圍。
- 手機端必須搭配 SSH 轉送，設定門檻高於一般 App。
- Service worker 的快取更新與除錯比一般靜態檔麻煩。

## 證據

- `README.md`「Install as an app」段：「The service worker (`/sw.js`) caches only static files …
  It never touches `/api/*`, so no mail is stored in the browser.」
- `docs/fmb/ARCHITECTURE.md` 第 8.5 節。
- `server/features/mobile.py` 提供 `sw.js`、manifest 與 `/api/mobile/info`。
