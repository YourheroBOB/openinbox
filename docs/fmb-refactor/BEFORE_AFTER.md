# 重構前後對照

以下片段的「後」都是**行為等價**的寫法；差異只在結構與命名。所有範例資料皆為虛構。

## 1. 回應組裝（D1，B4）

### 前

```python
@post("/api/agents/task")
def task(req):
    ...
    lang = _lang(req)
    result = run_task(kind, target or ask[:120], ask, lang)
    card = save_deliverable(result, lang=lang)
    return {"deliverable": card, "text": result["text"], "driver": result["driver"],
            "fallback": result["fallback"], "error": result["error"], "sources": result["sources"]}


@post("/api/agents/mention")
def mention(req):
    ...
    result = run_task(parsed["kind"], parsed["target"] or parsed["ask"][:120], parsed["ask"], lang, thread=item)
    card = save_deliverable(result, lang=lang)
    return {"triggered": True, "via": via, "mention": parsed, "deliverable": card, "text": result["text"],
            "driver": result["driver"], "fallback": result["fallback"], "error": result["error"],
            "sources": result["sources"]}
```

### 後

```python
RESULT_KEYS = ("text", "driver", "fallback", "error", "sources")


def _result_payload(result, card):
    """The response fields both task() and mention() return. One definition, one place to add a key."""
    payload = {k: result[k] for k in RESULT_KEYS}
    payload["deliverable"] = card
    return payload


@post("/api/agents/task")
def task(req):
    ...
    result = run_task(kind, target or ask[:120], ask, _lang(req))
    return _result_payload(result, save_deliverable(result, lang=_lang(req)))


@post("/api/agents/mention")
def mention(req):
    ...
    result = run_task(parsed["kind"], parsed["target"] or parsed["ask"][:120], parsed["ask"], lang, thread=item)
    return {"triggered": True, "via": via, "mention": parsed,
            **_result_payload(result, save_deliverable(result, lang=lang))}
```

`_lang(req)` 在 `task()` 內算兩次是刻意的：`run_task` 與 `save_deliverable` 各需一次，避免多一個區域變數稀釋可讀性；若要避免重複計算，抽到區域變數亦可，兩種都可接受。

## 2. 驅動派送與 fallback（D7／C1，B1）

### 前（`agents.py::run_task()` 節錄）

```python
def run_task(kind, target, ask="", lang="en", thread=None):
    import agent_bridge
    if kind not in TASK_KINDS:
        raise ValueError(f"unknown task kind: {kind}")
    pack = build_pack(kind, target, ask, lang, thread)
    cfg = agent_bridge.load_agent_cfg()
    driver = cfg.get("driver") or "local"
    text, used, error, fallback = "", driver, None, False
    try:
        if driver == "openai_compatible":
            text = agent_bridge._openai(pack, cfg).strip()
        elif driver == "cli":
            text = agent_bridge._cli(pack, cfg).strip()
        elif driver == "http":
            text = agent_bridge._http(pack, cfg).strip()
        else:
            used, fallback = "local", True
    except Exception as e:
        error, used, fallback = error_label(e), "local", True
    if not text:
        used, fallback = "local", True
        text = _local_brief(pack)
    return {"kind": kind, "target": target, "text": text, "driver": used,
            "fallback": fallback, "error": error, "sources": pack["sources"]}
```

### 後

```python
import agent_bridge  # 移到檔案頂端（B2 一併處理循環 import）


def run_task(kind, target, ask="", lang="en", thread=None):
    if kind not in TASK_KINDS:
        raise ValueError(f"unknown task kind: {kind}")
    pack = build_pack(kind, target, ask, lang, thread)
    done = agent_bridge.complete(pack)          # Completion(text, driver, fallback, error)
    text = done.text or _local_brief(pack)
    return {"kind": kind, "target": target, "text": text, "driver": done.driver,
            "fallback": done.fallback or not done.text, "error": done.error,
            "sources": pack["sources"]}
```

`agent_bridge.complete()` 的契約（B1 實作時寫進 docstring 並以測試固定）：

- `driver` 為設定值時照實回傳；呼叫失敗、逾時、回空字串或缺 driver 時，`driver` 一律為 `"local"` 且 `fallback` 為真。
- `error` 只放例外類名（可含 `HTTP <code>`），**不得**放外部端點回應本文、CLI stderr 或提示詞。
- 不得在 `complete()` 內呼叫任何寄送或遠端寫入路徑。

## 3. 來源正規化（D2／N7，B4）

### 前

```python
def _local_sources(target: str, limit: int = 8) -> list[dict]:
    if not target:
        return []
    out = []
    for e in yhbmail.list_emails(q=target, limit=limit):
        out.append({
            "id": e.get("id"), "subject": e.get("subject") or "",
            "from": e.get("from_addr") or "", "date": e.get("date_raw") or "",
            "snippet": (e.get("snippet") or "")[:300],
        })
    return out


def _thread_source(item: dict) -> dict:
    return {
        "id": item.get("id"), "subject": item.get("subject") or "",
        "from": item.get("from_addr") or "", "date": item.get("date_raw") or "",
        "snippet": (item.get("body_text") or item.get("snippet") or "")[:300],
    }
```

### 後

```python
def _mail_source(item: dict, prefer_body: bool = False) -> dict:
    """One cached message as an agent source. Snippet is capped at 300 chars."""
    snippet = (item.get("body_text") if prefer_body else None) or item.get("snippet") or ""
    return {
        "id": item.get("id"),
        "subject": item.get("subject") or "",
        "from": item.get("from_addr") or "",
        "date": item.get("date_raw") or "",
        "snippet": snippet[:300],
    }


def _local_sources(target: str, limit: int = 8) -> list[dict]:
    if not target:
        return []
    return [_mail_source(e) for e in yhbmail.list_emails(q=target, limit=limit)]
```

注意 `prefer_body=True` 時，`body_text` 為空字串會落回 `snippet`——與現況 `item.get("body_text") or item.get("snippet")` 一致。

## 4. 本機簡報文案表格化（L3／D6，B4）

### 前（節錄）

```python
    if kind == "meeting_prep":
        lines += (["## 會議準備", "- 目的：[待填]", "- 與會者：[待填]", "- 需要決定的事：[待填]", "- 行動項目：[待填]"]
                  if zh else
                  ["## Meeting prep", "- Goal: [missing]", "- Attendees: [missing]", "- Decisions needed: [missing]", "- Action items: [missing]"])
    elif kind == "research_company":
        lines += (["## 公司概況", "- 業務：[待填]", "- 近期動態：[待填]", "- 與我方關係：[待填]"]
                  if zh else
                  ["## Company brief", "- Business: [missing]", "- Recent news: [missing]", "- Relationship to us: [missing]"])
    else:
        lines += (["## 人物概況", "- 職務：[待填]", "- 與我方往來：[待填]", "- 近期溝通重點：[待填]"]
                  if zh else
                  ["## Person brief", "- Role: [missing]", "- Relationship to us: [missing]", "- Recent topics: [missing]"])
```

### 後

```python
BRIEF_SECTIONS = {
    "meeting_prep": {
        "zh": ("## 會議準備", ("目的", "與會者", "需要決定的事", "行動項目"), "[待填]"),
        "en": ("## Meeting prep", ("Goal", "Attendees", "Decisions needed", "Action items"), "[missing]"),
    },
    "research_company": {
        "zh": ("## 公司概況", ("業務", "近期動態", "與我方關係"), "[待填]"),
        "en": ("## Company brief", ("Business", "Recent news", "Relationship to us"), "[missing]"),
    },
    "research_person": {
        "zh": ("## 人物概況", ("職務", "與我方往來", "近期溝通重點"), "[待填]"),
        "en": ("## Person brief", ("Role", "Relationship to us", "Recent topics"), "[missing]"),
    },
}


def _brief_section(kind: str, zh: bool) -> list[str]:
    head, fields, blank = BRIEF_SECTIONS[kind]["zh" if zh else "en"]
    return [head] + [f"- {name}：{blank}" if zh else f"- {name}: {blank}" for name in fields]
```

新增 kind 時只改表格一處，`_local_brief()` 不再有 perl 式的三元鏈。

## 5. 卡片路徑與 id（D3／C5／N4，B3）

### 前

```python
def save_deliverable(result, lang="en", title=""):
    ...
    DELIV_DIR.mkdir(parents=True, exist_ok=True)
    (DELIV_DIR / f"{did}.md").write_text(_render_md(card), encoding="utf-8")
    (DELIV_DIR / f"{did}.html").write_text(_render_html(card), encoding="utf-8")
    (DELIV_DIR / f"{did}.json").write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")


def read_deliverable(did, fmt="md"):
    if not _valid_id(did) or fmt not in ("md", "html", "json"):
        return None
    p = DELIV_DIR / f"{did}.{fmt}"
    if not p.is_file():
        return None
    ...
```

### 後（`server/features/_deliverables.py`）

```python
FORMATS = {"md": "text/markdown; charset=utf-8",
           "html": "text/html; charset=utf-8",
           "json": "application/json; charset=utf-8"}


def card_path(did: str, fmt: str) -> pathlib.Path | None:
    """The only place a deliverables path is built. Invalid id or format returns None."""
    if not valid_id(did) or fmt not in FORMATS:
        return None
    return DELIV_DIR / f"{did}.{fmt}"


def make_id(kind: str, target: str) -> str:
    """Deterministic-ish id that always satisfies ID_RE, whatever the target contains."""
    slug = re.sub(r"[^a-z0-9]+", "-", (target or "").lower()).strip("-")[:40] or "card"
    raw = f"{kind.replace('_', '-')}-{slug}-{datetime.now(yhbmail.TZ).strftime('%Y%m%d-%H%M%S-%f')}".lower()
    did = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9-]", "-", raw)).strip("-")[:80].strip("-")
    if not valid_id(did):
        raise ValueError("bad deliverable id")
    return did
```

`save()`／`read()`／`list_cards()` 全部經 `card_path()`；`_valid_id()` 更名為 `valid_id()` 並只在此模組內使用。

## 6. 語言代碼（N1，B2）

### 前

```python
def _zh(lang) -> bool:
    return str(lang or "").lower().startswith("zh")


def _lang(req) -> str:
    return "zh" if req.lang_zh() else "en"
...
base = context_pack(ask=ask, skill="", lang="zh-Hant" if _zh(lang) else "en")
```

### 後

```python
# server/features/_i18n.py
def is_zh(lang) -> bool:
    """True for zh, zh-Hant, zh_TW, ZH-hant… Anything else is English."""
    return str(lang or "").lower().replace("_", "-").startswith("zh")


def code(is_zh: bool) -> str:
    """Short code stored in cards and responses: 'zh' or 'en'."""
    return "zh" if is_zh else "en"


def pack_lang(is_zh: bool) -> str:
    """BCP-47-ish code the context pack expects: 'zh-Hant' or 'en'."""
    return "zh-Hant" if is_zh else "en"


def pick(is_zh: bool, zh_text: str, en_text: str) -> str:
    return zh_text if is_zh else en_text
```

`agents.py` 端只保留 `_lang(req)` 這個薄包裝，其餘全改用 `_i18n` 的函式；`lang="zh"` 這個 dict 值維持不變以免破壞卡片格式。

## 7. UI 畫面拆分（L1，B5）

### 前（`ui/modules/agents.js`）

```js
  async function renderPane() {
    if (state.view !== "agents") return;
    if (view.preview) { /* 預覽分支：抓 md、設 iframe、wire() */ return; }
    if (view.tab === "cards") {
      if (!view.cards) await loadCards();
      if (state.view !== "agents" || view.preview || view.tab !== "cards") return;
      /* 成果清單分支 */ return;
    }
    /* 任務表單分支（含 @agent 區塊） */
  }
```

### 後

```js
  function renderPane() {
    if (state.view !== "agents") return;
    if (view.preview) return panePreview();
    if (view.tab === "cards") return paneCards();
    return paneTask();
  }

  function panePreview() { /* 原本的預覽分支；結尾 wire() */ }

  async function paneCards() {
    if (!view.cards) await loadCards();
    // 等待期間使用者可能已切換畫面：維持原本的重檢，不可省略。
    if (state.view !== "agents" || view.preview || view.tab !== "cards") return;
    /* 原本的成果清單分支；結尾 wire() */
  }

  function paneTask() { /* 原本的任務表單分支；結尾 wire() */ }
```

## 8. 別名與前綴（N2／N5／N6，B5）

### 前

```js
      mentionHint: "輸入 @agent（或 @research、@prep）開頭的訊息即可觸發；別名 {alias} 只作路由辨識，不收發信。",
...
      <p class="hint">${h(tf("mentionHint", { alias: "agent@example.com" }))}</p>
...
    box.innerHTML = `<div class="tag-form"><textarea class="tag-area" id="tagThreadText" ...`
```

### 後

```js
      mentionHint: "輸入 @agent（或 @research、@prep）開頭的訊息即可觸發；別名 {alias} 只作路由辨識，不收發信。",
      aliasFallback: "agent",
...
  // 別名由 GET /api/agents/deliverables 的 alias 欄位提供，UI 不再硬寫。
  async function loadAlias() {
    if (view.alias) return view.alias;
    try { view.alias = (await getJSON("/api/agents/deliverables?limit=1")).alias || t("aliasFallback"); }
    catch { view.alias = t("aliasFallback"); }
    return view.alias;
  }
...
      <p class="hint">${h(tf("mentionHint", { alias: await loadAlias() }))}</p>
...
    box.innerHTML = `<div class="agent-form"><textarea class="agent-area" id="agentThreadText" ...`
```

`loadAlias()` 只讀本機 API、失敗時退回中性字串，不會因為別名變更而與 server 不一致；同時 CSS class 與元素 id 統一為 `agent-` 前綴。
