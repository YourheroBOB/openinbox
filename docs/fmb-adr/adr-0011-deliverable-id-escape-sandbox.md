# ADR-0011：成果安全——ID 正則、全轉義、sandbox 預覽

- 狀態：已接受（現況仍有效）
- 日期：事後補建（原始決策日未記錄）
- 影響範圍：`server/features/agents.py`、`ui/modules/agents.js`
- 相關：ADR-0005、ADR-0014

## 背景

Agent 協作成果（人物研究、公司研究、會議準備）會同時寫成 Markdown、HTML、JSON 放到
`data/deliverables/`，再經 HTTP 提供預覽。兩類風險同時存在：

1. **路徑穿越**：如果直接用使用者可控字串組路徑，`../` 之類的 id 就能讀到資料夾外的檔案。
2. **XSS**：郵件文字與 Agent 輸出都是不可信內容，若原樣渲染成 HTML，可在面板上下文執行。

## 決策

1. **ID 白名單**：成果 id 必須符合 `^[a-z0-9][a-z0-9-]{2,80}$`；`save_deliverable` 產生 id 後
   再正則淨化並截斷；`read_deliverable`、`list_deliverables` 讀檔前都先驗證 stem。
2. **格式白名單**：只允許 `md`、`html`、`json`；不存在或非法一律 404，不組合任意路徑。
3. **全轉義**：`_render_html` 對每一行 `html.escape`；輸出不含 `<script>`、外部資源、
   inline event handler；CSS 內嵌且只用靜態值。
4. **前端雙層防護**：HTML 成果以 `sandbox=""` iframe 預覽（不給任何權限）；Markdown 以
   `textContent` 寫入，不做 HTML 注入；所有外來字串先過 `h()`。
5. 成果目錄在 gitignored 的 `data/` 下；清快取時一併移除（ADR-0008）。

## 取捨

| 考慮過的做法 | 為什麼沒有選 |
|---|---|
| 允許成果帶任意 HTML／圖表 | XSS 風險不可接受，且面板上下文就是本機 API |
| 引進 HTML sanitizer 依賴 | 違反零 pip；全轉義已足夠達成目標 |
| 用 `innerHTML` 渲染 Markdown | 等同執行不可信內容 |

## 後果

**正面**

- 路徑穿越與 XSS 都有明確防線，且可在測試中直接斷言（ID 正則、輸出無 script）。
- 預覽 HTML 成果不需要伺服端 sanitizer，行為可預期。

**負面／代價**

- 成果 Markdown 的呈現能力受限（無富文本、無內嵌互動圖表）。
- id 命名規則需維護；`sandbox=""` 也讓 HTML 內的連結、字型載入等行為受限。

## 證據

- `server/features/agents.py`：`ID_RE`、`_valid_id`、`_render_html`（`html.escape`、docstring
  「No script, no external resources, no inline event handlers」）、`read_deliverable` 的
  fmt 白名單與 404。
- `ui/modules/agents.js`：`<iframe class="tag-frame" sandbox="" src="…">`、`h()` 轉義函式、
  MD 預覽用 `el.textContent = md`。
