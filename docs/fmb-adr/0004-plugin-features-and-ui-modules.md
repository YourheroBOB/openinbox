# ADR 0004：外掛式 features 路由與自動載入 UI 模組

- 狀態：已接受（回溯整理；核心檔案有「最小掛勾」例外）
- 相關程式：`server/features/__init__.py`（`get`／`post`／`Raw`／`mount`）、`server/features/plugins.py`（`/api/features`、`/api/ui-modules`、`/ui/modules/*`）、`server/app.py`、`ui/index.html`、`ui/modules/*.js`

## 背景

這個 repo 的功能是**大量平行開發**的：統一收件匣、分流、撰寫、技能、搜尋、信件大腦、行事曆、信件操作、outbox、追蹤、代理協作、MCP、PWA……
如果每一個功能都要改 `server/app.py` 與 `ui/index.html`，那每條分支都會在同兩行相撞。
實際的 `state/*.md` 裡也一再出現「app.py、index.html 未改」這句話——那是刻意的成果，不是巧合。

## 決策

### 後端

1. 每支功能一支檔案：`server/features/<name>.py`。
2. 檔案內用裝飾器註冊路由：

   ```python
   from features import get, post

   @get("/api/hello")
   def hello(req):          # req.query、req.body、req.params、req.lang_zh()
       return {"hello": "world"}
   ```

3. `server/app.py` 只在啟動時把 features 掛上去（`features.mount(Handler)` 這類單一 hook），**之後不再改**。
4. 需要非 JSON 回應時用 `features.Raw(body, ctype)`。
5. 匯入失敗要**隔離**：`GET /api/features` 會列出已載入的功能、路由與載入錯誤，一支壞掉不該讓整個面板掛掉。

### 前端

6. 每支功能一支 UI 模組：`ui/modules/<name>.js`，由 `index.html` 的**單一 loader** 依 `GET /api/ui-modules` 清單動態載入。
7. 模組以「擴充核心」方式整合：掛側欄按鈕、覆寫／包裝核心的 `window.setView`／`window.openThread`、在 `state.view` 變成自己時渲染 `#pane`、監看 `document.documentElement.lang` 變化重新標字。
8. 模組必須自我防護：核心節點或 `state` 不存在就安靜 return，不要拋錯中斷其他模組。

### 例外

9. 少數東西天生屬於外殼，只能在 `ui/index.html` 加**最小掛勾**（例如 PWA 的 manifest／theme-color／圖示連結，以及提早攔截安裝事件的一行）。這類改動要在 PR 說明「為什麼不能放模組」，並保持逐行可回退。

## 取捨

**我們放棄**

- 顯式的路由表與模組註冊順序：現在是「檔案在，路由就在」，順序與相依變成隱含的。
- 集中式的 UI 翻譯檔與元件系統（見 ADR 0013）。

**我們得到**

- 平行開發幾乎不會在核心檔案衝突；merge 成本大幅下降。
- 功能可以整包移除（刪檔即消失），也容易在 `GET /api/features` 一眼看到載入了什麼。

**已知代價**

- 除錯要先看 `/api/features`（後端）與瀏覽器主控台（前端載入錯誤）。
- 核心與模組之間靠全域函式約定，沒有型別或介面契約；核心改名就是破壞性變更。

## 後果

- 新功能的第一個動作是「新增檔案」，不是「改 `app.py`」。
- 任何寫入端點記得加 Origin 檢查（ADR 0009）；任何回傳檔案的路徑記得驗證 id（ADR 0011）。
- UI 模組要自己處理：語言切換、重複渲染、深連結（`#view=…`）、以及其他模組可能已經改過 DOM 的情況。
- 若真的需要動核心檔案，改動要小、要雙語、要在 PR 說明，並預期審查會被問「能不能做成模組」。
