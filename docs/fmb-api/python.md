# Python API 參考

本頁記錄本次提供的 `server/features/agents.py` 與 `server/persona.py` 中，名稱不以下底線開頭的函式。函式使用本機快取與設定；部分函式可能透過已設定的 BYO Agent 執行外部呼叫。

## `server.features.agents`

### `parse_mention(text: str) -> dict | None`

解析文字中第一個支援的 agent 提及。

**參數**

- `text`：待解析文字；最多處理前 4000 字元。

**回傳**

找不到支援的提及時回傳 `None`。找到時回傳字典：

- `kind`：`research_person`、`research_company` 或 `meeting_prep`。
- `target`：提及後同一行的目標文字，最多 120 字元。
- `word`：識別到的提及別名。
- `ask`：移除提及字詞後、空白正規化的完整請求文字，最多 1000 字元。

此函式是純解析函式，不讀取快取或呼叫 Agent。

**錯誤**

提及任務種類由內部規則推斷；本函式未定義自訂錯誤回傳。

**範例**

```python
from features.agents import parse_mention

parsed = parse_mention("@research <測試對象> 摘要本機往來重點")
if parsed:
    print(parsed["kind"], parsed["target"])
```

### `mentions_alias(to_addr: str) -> bool`

檢查收件人地址清單中是否有精確符合 agent routing alias 的地址。

**參數**

- `to_addr`：收件人欄位文字；支援的分割及地址解析方式由 `features.compose` 提供。

**回傳**

- `True`：至少一個解析後的地址與 alias 完全相同（不區分大小寫）。
- `False`：沒有精確符合地址。

本函式只做路由辨識，不會投遞郵件。

**錯誤**

底層地址解析模組不可用時，可能傳遞其匯入或執行錯誤；無自訂錯誤格式。

**範例**

```python
from features.agents import mentions_alias

is_routed = mentions_alias("<recipient list>")
```

### `build_pack(kind: str, target: str, ask: str = "", lang: str = "en", thread: dict | None = None) -> dict`

建立交給 Agent bridge 的本機 context pack。

**參數**

| 參數 | 說明 |
|---|---|
| `kind` | 必須是 `TASK_KINDS` 之一。 |
| `target` | 研究對象文字。 |
| `ask` | 任務補充內容。 |
| `lang` | 語言提示；以 `zh` 開頭時使用繁中 context，否則使用英文。 |
| `thread` | 可選的本機快取郵件字典；若提供，該郵件來源會排在其他來源之前。 |

**回傳**

字典包含 `task`、`target`、`ask`、`lang`、`persona`、`sources`、`brain` 與 `rules`。來源只從本機郵件快取擷取；每筆來源包含 `id`、`subject`、`from`、`date`、`snippet`。

**錯誤**

- `ValueError`：`kind` 不在支援清單。
- 其他資料或 context 建立錯誤可能由相關模組傳遞。

**範例**

```python
from features.agents import build_pack

pack = build_pack(
    kind="meeting_prep",
    target="<測試對象>",
    ask="整理待確認事項",
    lang="zh-Hant",
)
```

### `error_label(exc: BaseException) -> str`

將例外轉成不含原始錯誤訊息本文的安全標籤。

**參數**

- `exc`：待標示例外。

**回傳**

例外類別名稱；若例外的 `code` 屬性為整數，或訊息中可解析出 HTTP 狀態碼，則附加 `HTTP <狀態碼>`。不回傳原始例外訊息。

**錯誤**

本函式未定義自訂錯誤格式。

**範例**

```python
from features.agents import error_label

label = error_label(RuntimeError("example failure"))
```

### `run_task(kind: str, target: str, ask: str = "", lang: str = "en", thread: dict | None = None) -> dict`

建立 context pack，呼叫設定的 Agent driver，並在失敗或無文字時退回本機啟發式。

**參數**

| 參數 | 說明 |
|---|---|
| `kind` | 必須是 `TASK_KINDS` 之一。 |
| `target` | 任務目標。 |
| `ask` | 任務補充內容。 |
| `lang` | 輸出語言提示。 |
| `thread` | 可選的本機快取郵件，會成為優先來源。 |

**回傳**

字典包含 `kind`、`target`、`text`、`driver`、`fallback`、`error` 與 `sources`。錯誤內容會經 `error_label` 安全化；fallback 文字由本機啟發式產生。

**錯誤**

- `ValueError`：`kind` 不支援。
- context pack 建立過程中的錯誤可能向外傳遞。
- Agent 呼叫錯誤本身會被捕捉並改用 fallback。

**範例**

```python
from features.agents import run_task

result = run_task(
    kind="research_person",
    target="<測試對象>",
    ask="僅整理本機來源支持的事實",
    lang="zh-Hant",
)
```

### `save_deliverable(result: dict, lang: str = "en", title: str = "") -> dict`

將任務結果儲存為本機成果卡片。

**參數**

- `result`：至少需提供有效 `kind`；可含 `target`、`text`、`driver`、`fallback` 與 `sources`。
- `lang`：輸出語言提示；以 `zh` 開頭時成果語言標記為 `zh`。
- `title`：可選的自訂標題。

**回傳**

卡片 metadata 字典：`id`、`title`、`kind`、`target`、`lang`、`created`、`driver`、`fallback`。

**副作用**

在 `data/deliverables/` 建立 `.md`、`.html` 與 `.json` 檔案。HTML 內容會轉義，不使用腳本或外部資源。

**錯誤**

若產生的 ID 不符合格式，會引發 `ValueError`。無效 `kind` 或缺少必要 `result` 欄位可能造成索引錯誤。

**範例**

```python
from features.agents import save_deliverable

card = save_deliverable(
    {
        "kind": "research_company",
        "target": "<測試對象>",
        "text": "僅供文件測試的結果。",
        "driver": "local",
        "fallback": True,
        "sources": [],
    },
    lang="zh-Hant",
)
```

### `list_deliverables(limit: int = 50) -> list[dict]`

讀取並列出本機成果卡片 metadata。

**參數**

- `limit`：回傳項目數上限；此 Python 函式本身不會將值限制在 HTTP 路由使用的範圍。

**回傳**

依 `created` 由新至舊排序的 metadata 清單。每筆包含 `id`、`title`、`kind`、`target`、`lang`、`created`、`driver`、`fallback`。目錄不存在時回傳空清單；無法解析或讀取的卡片會略過。

**錯誤**

讀取單筆卡片時的 `OSError` 與 JSON 格式錯誤會略過；其他錯誤未定義自訂格式。

**範例**

```python
from features.agents import list_deliverables

cards = list_deliverables(limit=10)
```

### `read_deliverable(did: str, fmt: str = "md") -> tuple[bytes, str] | None`

讀取指定成果卡片檔案。

**參數**

- `did`：成果卡片 ID，須符合嚴格 ID 格式。
- `fmt`：`md`、`html` 或 `json`。

**回傳**

成功時回傳 `(內容位元組, Content-Type)`；ID、格式或檔案不存在時回傳 `None`。

**錯誤**

不合法 ID、未支援格式或檔案不存在均以 `None` 表示；不組合未經驗證的任意路徑。

**範例**

```python
from features.agents import read_deliverable

data = read_deliverable("<成果卡片 ID>", "md")
```

### HTTP 路由處理函式

以下函式由功能路由註冊器使用，不是建議由應用程式直接呼叫的穩定 Python 契約。

| 函式 | 註冊路徑 | 輸入 | 回傳 |
|---|---|---|---|
| `task(req)` | `POST /api/agents/task` | 請求物件；讀取 `req.body`、`req.lang_zh()` | JSON-compatible dict，或 `(dict, status)`。 |
| `mention(req)` | `POST /api/agents/mention` | 請求物件；讀取 `req.body`、`req.lang_zh()` | JSON-compatible dict，或 `(dict, status)`。 |
| `deliverables(req)` | `GET /api/agents/deliverables` | 請求物件；讀取 `req.query`、`req.lang_zh()` | 含 `deliverables` 與 `alias` 的字典，或拒絕回應。 |
| `deliverable(req)` | `GET /api/agents/deliverables/*` | 請求物件；讀取 `req.params`、`req.lang_zh()` | `Raw` 回應，或 404 JSON。 |

## `server.persona`

### `rebuild() -> dict`

依本機郵件快取、Second Brain 看板、帳號設定及可選示範種子重建人格資料。

**參數**

無。

**回傳**

人格字典，包含 `updated_at`、`mode`、`identity`、`how_you_write`、`how_you_run_inbox`、`attention_now`、`inbox_priorities`、`top_senders`、`facts_learned`、`source`。

**副作用**

寫入 vault 內的人格 JSON 與 Markdown 檔案。

**錯誤**

檔案讀取、JSON 解析、資料庫或 vault 寫入錯誤可能向外傳遞；未定義統一錯誤格式。

**範例**

```python
from persona import rebuild

profile = rebuild()
```

### `load() -> dict`

載入已儲存的人格資料；若人格 JSON 不存在，呼叫 `rebuild()` 建立。

**參數**

無。

**回傳**

人格字典，欄位同 `rebuild()`。

**錯誤**

既有 JSON 無法解析或重建資料失敗時，底層錯誤可能向外傳遞。

**範例**

```python
from persona import load

profile = load()
```
