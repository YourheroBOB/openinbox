# openinbox 問題清單

> 行號為約略錨點；修補前請以 `grep -n` 確認。所有程式片段都是「建議寫法」，尚未套用。

## 總表

| ID | 檔案／錨點 | 嚴重度 | 類別 | 問題摘要 |
|---|---|---:|---|---|
| A1 | `server/features/agents.py` `save_deliverable()` 約 250-285 行 | 高 | 正確性／併發 | 成果檔非原子寫入，MD/HTML/JSON 可能只寫一半 |
| A2 | `server/features/agents.py` `list_deliverables()` 約 287-302 行 | 中 | 正確性 | 只依分鐘精度 `created` 排序，同分鐘卡片順序不穩定 |
| A3 | `server/features/agents.py` `COMPANY_WORDS` 約 56-62 行 | 中 | 正確性 | `inc`、`corp` 等無詞界，誤判 `include`、`principal` 為公司 |
| A4 | `server/features/agents.py` `list_deliverables()` 與 `ui/modules/agents.js` `loadCards()` 約 128-141 行 | 中 | 錯誤處理 | 讀取失敗被吞掉，UI 顯示「還沒有成果」而非錯誤 |
| A5 | `server/features/agents.py` `_local_sources()` 約 116-129 行 | 中 | 安全／相依 | `q=target` 直接進入搜尋層，FTS 運算子可能改變查詢語意 |
| A6 | `server/features/agents.py` `run_task()` 約 224-246 行 | 中 | 相依風險 | 直接呼叫 `agent_bridge._openai/_cli/_http` 私有函式 |
| A7 | `server/features/agents.py` `error_label()` 約 210-218 行 | 低 | 正確性 | `bool` 是 `int` 子類，`code=True` 會變成 `HTTP True` |
| A8 | `ui/modules/agents.js` `renderPane()` 約 158-205 行 | 中 | 正確性／併發 | 非同步 render 無取消 token，快速切換可能寫入過期內容 |
| A9 | `ui/modules/agents.js` `runTask()/runMention()/runThreadMention()` | 低 | 錯誤處理 | 非 JSON 回應或 `fetch` 失敗時，部分路徑只顯示失敗文字 |
| A10 | `server/features/agents.py` `_render_html()` 約 232-249 行 | 低 | 可讀性／無障礙 | 連續 `<li>` 沒有包在 `<ul>` 內，語意與螢幕閱讀器較差 |
| A11 | `server/features/agents.py` `mention()` 約 330-372 行 | 低 | 錯誤處理 | `mentions_alias()` 內動態匯入 `features.compose`，匯入失敗會變 500 |
| A12 | `server/features/agents.py` `REQUEST_VERBS` / `MEETING_WORDS` 約 57-66 行 | 低 | 可讀性／可測試性 | 正則複雜且已有誤判面，缺單元測試釘住行為 |

---

## A1 成果檔非原子寫入

**檔案**：`server/features/agents.py` `save_deliverable()` 約 250-285 行  
**嚴重度**：高  
**類別**：正確性、併發、錯誤處理

**說明**：`save_deliverable()` 依序寫入 `{id}.md`、`{id}.html`、`{id}.json`。若在 HTML 寫入後、JSON 寫入前發生例外或程序中斷，會留下 MD/HTML 存在但 JSON 缺失的半成品。`list_deliverables()` 只讀 JSON，所以這個壞卡不會出現在清單；但 `read_deliverable()` 可以在知道 JSON 的情況下直接讀 MD/HTML。 concurrent requests 同時為相似 target 建卡時，也更容易產生競態。

**建議修法**：同一目錄寫暫存檔後 `os.replace`，並把 JSON 當成 commit marker；MD/HTML 寫完後才寫 JSON。讀取與清單都要求 JSON 存在。

```python
import os
import tempfile
from pathlib import Path


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_deliverable(result: dict, lang: str = "en", title: str = "") -> dict:
    # ... existing validation/card build ...
    DELIV_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_write(DELIV_DIR / f"{did}.md", _render_md(card))
    _atomic_write(DELIV_DIR / f"{did}.html", _render_html(card))
    _atomic_write(DELIV_DIR / f"{did}.json", json.dumps(card, ensure_ascii=False, indent=2))
    return {k: card[k] for k in ("id", "title", "kind", "target", "lang", "created", "driver", "fallback")}
```

**驗收建議**：用 `tmp_path` 模擬 `_atomic_write` 在 JSON 前拋錯，確認沒有孤立 MD/HTML 被 `list_deliverables()` 或 `read_deliverable()` 視為有效卡。

---

## A2 成果排序不穩定

**檔案**：`server/features/agents.py` `list_deliverables()` 約 287-302 行  
**嚴重度**：中  
**類別**：正確性

**說明**：`created` 使用 `%Y-%m-%d %H:%M`，只到分鐘；`_stamp()` 雖有微秒但只在 `id` 內。同一分鐘建立多張卡時，`cards.sort(key=created)` 的順序會受 `glob()` 順序影響，可能不穩定，`limit` 截斷也可能漏掉最新卡。

**建議修法**：排序加入 `id` tie-breaker；更穩定的做法是在 card 內保存可排序的 `stamp` 或讓 `created` 含秒。

```python
cards.sort(key=lambda c: ((c.get("created") or ""), (c.get("id") or "")), reverse=True)
```

**驗收建議**：建立同分鐘多卡，確認清單順序可重現；`limit=1` 取到 `stamp` 最新者。

---

## A3 公司關鍵字誤判

**檔案**：`server/features/agents.py` `COMPANY_WORDS` 約 56-62 行；`parse_mention()` 約 96-114 行  
**嚴重度**：中  
**類別**：正確性

**說明**：`COMPANY_WORDS = re.compile(r"(公司|company|corp|inc|ltd|co\.|股份|有限)", re.I)` 沒有詞界。英文子字串會誤判：`include`、`principal`、`since` 都含 `inc`；`scope` 含 `co` 但因模式是 `co\.` 不會誤判，而 `inc` 已足以造成問題。這會讓 `@agent` 的一般請求被路由成 `research_company`。

**建議修法**：英文缩写加詞界；中文維持子字串。補測試釘住 `include`、`principal`、`Acme Inc`。

```python
COMPANY_WORDS = re.compile(
    r"(?:公司|company|corporation|\bcorp\b|\binc\b|\bltd\b|\bco\b|股份|有限)",
    re.I,
)
```

**驗收建議**：`parse_mention("@agent include the principal update")` 應為 `research_person`；`parse_mention("@agent Acme Inc recent threads")` 應為 `research_company`。

---

## A4 成果讀取失敗被吞掉

**檔案**：`server/features/agents.py` `list_deliverables()` 約 287-302 行；`ui/modules/agents.js` `loadCards()/cardsHtml()` 約 128-157 行  
**嚴重度**：中  
**類別**：錯誤處理、可診斷性

**說明**：`list_deliverables()` 對 `OSError`／`JSONDecodeError` 直接 `continue`；UI `loadCards()` 雖存 `error`，但 `cardsHtml()` 只看 `deliverables`，所以磁碟或 JSON 壞掉時，使用者看到「還沒有成果卡片」而不是「讀取失敗」。這會讓 A1 的半成品更難被發現。

**建議修法（產品碼，尚未套用）**：API 可回報略過的成功／失敗计数，UI 顯示錯誤。例：

```python
skipped = 0
for p in DELIV_DIR.glob("*.json"):
    # ...
    except (OSError, json.JSONDecodeError):
        skipped += 1
        continue
# return {"deliverables": cards[:limit], "skipped": skipped}
```

```js
function cardsHtml() {
  if (view.cards?.error) return `<div class="tag-err">${h(t("failed") + view.cards.error)}</div>`;
  const items = view.cards?.deliverables || [];
  // ...
}
```

**注意**：這會改變 API 回應形狀，需確認舊客戶端可忽略新欄位。

---

## A5 本地來源查詢未隔離搜尋語法

**檔案**：`server/features/agents.py` `_local_sources()` 約 116-129 行  
**嚴重度**：中  
**類別**：安全、相依風險

**說明**：`_local_sources()` 把 `target` 直接傳給 `yhbmail.list_emails(q=target, ...)`。若底層是 FTS5 `MATCH`，引號、`*`、`OR`、`NEAR`、括號可能改變查詢語意；若底層是 `LIKE` 則主要是逸出問題。由於任務未提供 `yhbmail.py`／`search.py`，此項標為待確認，但輸入邊界應收斂。

**建議修法**：在 `search.py` 提供 `escape_query()`，或讓 `_local_sources()` 只接受已轉義的查詢；不要把原始 target 當成查詢語言。

```python
# search.py (proposal)
def escape_query(q: str) -> str:
    return '"' + q.replace('"', '""') + '"'
```

**驗收建議**：測試 `target='" OR 1=1'`、`target='NEAR(a b)'`、`target='***'` 不會拋錯，也不會擴大成全表搜尋。

---

## A6 功能層呼叫 agent_bridge 私有函式

**檔案**：`server/features/agents.py` `run_task()` 約 224-246 行  
**嚴重度**：中  
**類別**：相依風險、可測試性

**說明**：`run_task()` 直接呼叫 `agent_bridge._openai(pack, cfg)`、`agent_bridge._cli(...)`、`agent_bridge._http(...)`。私有函式名稱與簽章隨時可能改；功能層與橋接層耦合後，測試也必須知道私有介面。

**建議修法**：在 `agent_bridge` 提供公開進入點，功能層只依賴公開 API。

```python
# agent_bridge.py (proposal)
def run_driver(pack: dict, cfg: dict) -> str:
    driver = cfg.get("driver") or "local"
    if driver == "openai_compatible":
        return _openai(pack, cfg)
    if driver == "cli":
        return _cli(pack, cfg)
    if driver == "http":
        return _http(pack, cfg)
    raise ValueError("local driver has no remote call")
```

`server/features/agents.py` 改呼叫 `agent_bridge.run_driver(pack, cfg)`，並把 `local` 分支留在功能層。

---

## A7 `error_label()` 會把布林當 HTTP 狀態

**檔案**：`server/features/agents.py` `error_label()` 約 210-218 行  
**嚴重度**：低  
**類別**：正確性

**說明**：`code = getattr(exc, "code", None)`；`if not isinstance(code, int)` 會放過 `True`／`False`，因為 `bool` 是 `int` 子類，最後可能輸出 `RuntimeError: HTTP True`。

**建議修法**：

```python
if isinstance(code, int) and not isinstance(code, bool):
    return f"{label}: HTTP {code}"
```

---

## A8 前端非同步 render 無取消

**檔案**：ui/modules/agents.js `renderPane()` 約 158-205 行  
**嚴重度**：中  
**類別**：正確性、併發

**說明**：`renderPane()` 在 cards/preview 路徑有 `await loadCards()`／`await fetch(...)`。若使用者在等待期間切換 view 或 tab，舊請求完成後仍可能寫入 `#pane`。cards 路徑有部分防護，但 task 路徑與 preview MD 路徑不足。

**建議修法**：引入 render token，舊 render 在寫入前檢查。

```js
let renderToken = 0;

async function renderPane() {
  const my = ++renderToken;
  // ... existing sync render ...
  if (needsCards) {
    await loadCards();
    if (my !== renderToken || state.view !== "agents") return;
    $pane().innerHTML = ...;
  }
}
```

---

## A9 UI 對 fetch 失敗的呈現不一致

**檔案**：ui/modules/agents.js `loadCards()/runTask()/runMention()/runThreadMention()`  
**嚴重度**：低  
**類別**：錯誤處理、可讀性

**說明**：`getJSON()` 沒有包一層錯誤正規化；`postJSON()` 會對 `!r.ok || d.error` 拋錯，但若伺服器回 HTML 錯誤頁，`r.json()` 會拋 `SyntaxError`，訊息對使用者不友好。`loadCards()` 也會把錯誤藏成空清單（見 A4）。

**建議修法**：統一 `fetchJSON` 錯誤正規化，保留 `status` 與安全訊息，不顯示端點原始 body。

```js
const fetchJSON = async (path, opts) => {
  const r = await fetch(path, opts);
  const text = await r.text();
  let d = {};
  try { d = JSON.parse(text); } catch { throw new Error(`bad response (${r.status})`); }
  if (!r.ok || d.error) throw new Error(d.error || `request failed (${r.status})`);
  return d;
};
```

---

## A10 成果 HTML 清單語意不完整

**檔案**：`server/features/agents.py` `_render_html()` 約 232-249 行  
**嚴重度**：低  
**類別**：可讀性、無障礙

**說明**：Markdown 的 `- ` 行被轉成獨立 `<li>`，但沒有包在 `<ul>` 內。多個 `<li>` 散落在 `<body>` 下，語意不佳，螢幕閱讀器可能不公告「清單」。

**建議修法**：把連續 `<li>` 包成 `<ul>`。

```python
paras: list[str] = []
open_list = False
for ln in card["text"].splitlines():
    s = ln.rstrip()
    if not s:
        continue
    if s.lstrip().startswith("- "):
        if not open_list:
            paras.append("<ul>")
            open_list = True
        paras.append(f"<li>{esc(s.lstrip()[2:])}</li>")
        continue
    if open_list:
        paras.append("</ul>")
        open_list = False
    # ... headings/paragraph ...
if open_list:
    paras.append("</ul>")
```

---

## A11 `mention()` 動態匯入 compose 可能 500

**檔案**：`server/features/agents.py` `mentions_alias()` 約 107-114 行；`mention()` 約 330-372 行  
**嚴重度**：低  
**類別**：錯誤處理、相依風險

**說明**：`mentions_alias()` 在函式內 `from features.compose import parse_addr, split_addrs`。若 `compose` 模組載入失敗或有循環匯入問題，`POST /api/agents/mention` 會直接 500，而不是回可診斷的 fallback。

**建議修法**：把匯入移到模組頂層，或在 `mention()` 內 catch `ImportError` 並回 `{"error": "address parser unavailable"}`、500 只留類型不留堆疊。需確認 `features.compose` 不會造成循環匯入。

---

## A12 提及正則缺測試與解說

**檔案**：`server/features/agents.py` `REQUEST_VERBS` / `MEETING_WORDS` 約 57-66 行  
**嚴重度**：低  
**類別**：可讀性、可測試性

**說明**：`REQUEST_VERBS` 同時處理前綴與後綴，可讀性較差；`MEETING_WORDS` 含 `prep`、`call`，可能把 `callback`、`recall` 誤判成會議。目前雖有 agents 相關測試，但建議把這些邊界樣例明確釘住。

**建議修法**：拆成 `REQUEST_PREFIX_RE`、`REQUEST_SUFFIX_RE`，並補測試：

```python
REQUEST_PREFIX_RE = re.compile(r"^(?:please|pls|can you|could you|請幫我|幫我|麻煩|查一下|幫忙)\s*|^(?:查|研究)\s+", re.I)
REQUEST_SUFFIX_RE = re.compile(r"\s*(?:please|pls|請幫我查|請查|幫我查|查一下)$", re.I)
MEETING_WORDS = re.compile(r"(?:會議|meeting|agenda|議程|prep|準備)", re.I)
```

**注意**：移除 `call` 是行為變更，需 BOB 確認是否接受。
