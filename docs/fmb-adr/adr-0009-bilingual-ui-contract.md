# ADR-0009：雙語 UI 契約——每個字串繁中與英文成對，禁止簡體

- 狀態：已接受（現況仍有效）
- 日期：事後補建（原始決策日未記錄）
- 影響範圍：`ui/index.html`、`ui/modules/*.js`、`skills/*.md`、所有回傳給前端的訊息
- 相關：ADR-0002

## 背景

主要使用者是繁體中文使用者，但專案要能對外（英文）說明與分享。團隊刻意不引進 i18n 框架
或語言檔管線，以維持「沒有建置步驟、沒有 npm」的特性（ADR-0001）。

## 決策

1. 每個介面字串**同時**提供 `zh`（繁體中文）與 `en`；慣例是在同一模組內放
   `S = { zh: {…}, en: {…} }`，前端依 `document.documentElement.lang` 取用。
2. 服務端用 `req.lang_zh()` 判斷語系，回傳給前端的訊息同樣雙語。
3. 語系切換：左側按鈕、`?lang=zh-Hant`／`?lang=en`；模組需監聽 `lang` 變更重繪。
4. 技能檔 `skills/*.md` 採「繁體中文在前、英文在後」的雙語 markdown。
5. **禁止簡體中文**。
6. 不抽共用語言檔、不引進翻譯工具鏈；字串跟著功能模組走。

## 取捨

| 考慮過的做法 | 為什麼沒有選 |
|---|---|
| i18n 框架＋語言 JSON | 違反零建置；增加載入與同步成本 |
| 只做單一語言 | 排除英文讀者與對外分享 |
| 伺服端統一文案表 | 前端自含字典才能讓外Plug-in模組自足（ADR-0002） |

## 後果

**正面**

- 沒有建置步驟、沒有語言檔漂移問題。
- 新增功能時，雙語字串在同一個 dict 裡，review 一眼看得見缺漏。
- `ui/modules/agents.js` 等模組可被完整複製當範本。

**負面／代價**

- 相同字串在不同模組重複；沒有自動化鍵集合檢查（ROADMAP 第 9 項列為待辦）。
- 語言字典越來越大時，模組可讀性下降。

## 證據

- `CONTRIBUTING.md`：「UI strings go in both `zh-Hant` and `en` in `ui/index.html`. No simplified Chinese.」
- `README.md`「Switch language with 繁中 / EN, or `?lang=…`」。
- `ui/modules/agents.js` 開頭的 `S = { zh: {...}, en: {...} }` 與 `isZh()`／`langParam()`。
- `skills/*.md` 皆為「中文標題 / English title」雙語格式。
