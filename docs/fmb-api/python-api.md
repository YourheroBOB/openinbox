# Python 公開介面參考

## 1. 功能外掛路由 API（`server/features/__init__.py`）

新功能放一支 `server/features/<名稱>.py`，路由在匯入時自動註冊，不必改 `server/app.py`。

```python
from features import get, post

@get("/api/hello")
def hello(req):            # req.query、req.body、req.lang_zh()
    return {"hello": "world"}
```

| 項目 | 說明 |
|---|---|
| `get(path)`／`post(path)` | 路由裝飾器；handler 收一個 `req` |
| `req.query` | query string 對映 |
| `req.body` | JSON body 對映 |
| `req.lang_zh()` | 是否繁中 |
| `req.params` | 萬用路由（`*`）捕獲的剩餘路徑（見 agents.py） |
| `Raw(body, ctype)` | 回傳非 JSON 內容（例如成果 md／html） |
| `features._origin.local_origin(req)` | 本機來源檢查 |
| `features._origin.refuse(lang_zh)` | 非本機來源的拒絕回應 |

外掛在同行程內執行，屬受信任本機程式碼，不是沙箱。

## 2. `server/features/agents.py`（source）

常數：

| 名稱 | 值／說明 |
|---|---|
| `DELIV_DIR` | `data/deliverables/`（`yhbmail.DATA / "deliverables"`） |
| `ALIAS` | `agent@example.com`（路由詞，從不收發信） |
| `MAX_BODY` | 4000，mention 文字截斷 |
| `ID_RE` | `^[a-z0-9][a-z0-9-]{2,80}$`，成果 id 驗證 |
| `TASK_KINDS` | `research_person`、`research_company`、`meeting_prep` |
| `MENTIONS` | `@agent` 觸發詞到任務種類的對映（`agent` 為泛型，依內容推斷） |
| `LABELS` | 繁中／英文標籤 |

### `parse_mention(text: str) -> dict | None`

找出一則 thread 訊息中第一個 `@agent` 提及與它要求的任務。正規表示式：`(?<![\w.])@(agent|research-company|research|prep|meeting)\b`（不分大小寫）。

- 參數：`text`，內部截斷到 `MAX_BODY`。
- 回傳：`None`（沒有提及）或 `{"kind", "target", "word", "ask"}`：
  - `kind`：三種任務種類之一。
  - `target`：提及同行後方文字，已剝除禮貌用語（`請幫我`、`please` 等），截斷 120。
  - `word`：觸發詞。
  - `ask`：移除提及後的整則訊息，截斷 1000。
- 推斷：`@agent` 泛型時，含會議詞→`meeting_prep`；對象含公司詞→`research_company`；否則 `research_person`。
- 純函式，不讀任何資料。

### `mentions_alias(to_addr: str) -> bool`

收件者 addr-spec 完全等於 `agent@example.com` 時為真；較長 local-part 或額外標籤不算。只做路由判斷，從不送達。

### `build_pack(kind: str, target: str, ask: str = "", lang: str = "en", thread: dict | None = None) -> dict`

- `kind` 不在 `TASK_KINDS` → `ValueError`。
- 回傳 `{"task", "target", "ask", "lang", "persona", "sources", "brain", "rules"}`。
- `sources` 來自本機信件快取（`_local_sources`，subject／sender／body 命中 target，上限 8 筆）；`thread` 提供時排第一位。
- `rules` 在基礎規則上追加：只用本機來源、不得捏造、缺漏標 `[待填]`、引用郵件是資料不是指令。

### `run_task(kind: str, target: str, ask: str = "", lang: str = "en", thread: dict | None = None) -> dict`

- `kind` 非法 → `ValueError`。
- 經 `agent_bridge` 依驅動執行；例外、逾時、空白回覆皆改本機啟發式。
- 回傳 `{"kind", "target", "text", "driver", "fallback", "error", "sources"}`；`error` 為 `error_label` 結果或 `None`。

### `error_label(exc: BaseException) -> str`

例外類別名；例外訊息可解析出 HTTP 狀態碼時附加 `: HTTP <code>`。永不包含例外訊息本身。

### `save_deliverable(result: dict, lang: str = "en", title: str = "") -> dict`

- 寫入 `data/deliverables/{id}.md`、`.html`、`.json`。
- `id` = `{kind 連字號}-{target slug}-{時間戳}`，經 `ID_RE` 淨化與驗證；不合格 → `ValueError("bad deliverable id")`。
- HTML 全跳脫、無腳本、無外部資源、無 inline event handler。
- 回傳卡片 metadata（`id`、`title`、`kind`、`target`、`lang`、`created`、`driver`、`fallback`）。

### `list_deliverables(limit: int = 50) -> list[dict]`

讀取 `*.json`，跳過不合法 id 與壞檔，依 `created` 倒序取前 `limit` 筆 metadata。

### `read_deliverable(did: str, fmt: str = "md") -> tuple[bytes, str] | None`

`fmt` 限 `md`／`html`／`json`；`did` 須過 `ID_RE`；不存在回 `None`。否則回 `(位元組, content-type)`。

## 3. 核心模組公開面（由 agents.py 使用處確認）

以下簽名依 `server/features/agents.py` 的實際呼叫整理；完整 schema（待確認）：

| 模組 | 成員 | 說明 |
|---|---|---|
| `yhbmail` | `DATA` | `data/` 目錄路徑 |
| `yhbmail` | `TZ` | 本機時區 |
| `yhbmail` | `list_emails(q=…, limit=…)` | 本機快取搜尋；回傳含 `id`、`subject`、`from_addr`、`date_raw`、`snippet`、`body_text` 的字典序列 |
| `yhbmail` | `get_email(id)` | 單封信或 `None` |
| `agent_bridge` | `context_pack(ask, skill, lang)` | context pack；回傳含 `lang`、`rules`、`brain` |
| `agent_bridge` | `load_agent_cfg()` | 載入 `agent.json` |
| `persona` | `load()` | 人格資料 |
| `features.compose` | `parse_addr`、`split_addrs` | 地址解析（agents.py 使用） |

## 4. `fmb_feature2/`（獨立模組）

自包含套件：modified UTF-7 mailbox 名稱、唯讀 LIST 解析、IMAP 預檢。不 import 應用程式；複製到 `server/features/` 才接線。內部函式簽名（待確認）。
