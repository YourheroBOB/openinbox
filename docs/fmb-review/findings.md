# openinbox 具體審查發現

## F-01 — Deliverable 三檔非原子寫入，可能出現半套結果

- **檔案／行號：** `server/features/agents.py:308-331, 335-358`
- **嚴重度：** High
- **類別：** 正確性、併發、錯誤處理

### 說明

`save_deliverable()` 依序寫入 `.md`、`.html`、`.json`。若程序在任一寫入點中止，會留下：

- 只有 Markdown、沒有 JSON，列表 API 不會顯示；
- JSON 已完成但 HTML 尚未完成，預覽行為不一致；
- `list_deliverables()` 遇到暫時不完整 JSON 時直接略過該卡片，沒有 repair 或告警。

ID 雖含微秒時間戳，但沒有獨占建立或 compare-and-swap；兩個高度併發的請求仍可能覆寫同名 ID。`read_deliverable()` 也採「先檢查、後讀取」，檔案在兩步之間消失會拋出未處理例外。

### 建議修法

使用不可變、內容導向 ID；每個檔案先寫同目錄暫存檔，再以 `os.replace()` 原子替換。卡片 metadata 以 SQLite transaction 或單一 manifest 為權威索引。

```python
import os
import tempfile
import uuid
from pathlib import Path


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def new_deliverable_id(kind: str, target: str) -> str:
    # 唯一性由 UUID 負責，不依賴時間戳碰撞假設。
    return f"{kind.replace('_', '-')}-{uuid.uuid4().hex[:16]}"
```

## F-02 — Second Brain ID namespace 混用，存在覆蓋人工卡片與遺失更新風險

- **檔案／行號：** `server/second_brain.py:14-16, 37-71, 93-108`
- **嚴重度：** High
- **類別：** 正確性、併發、資料遺失

### 說明

人工卡片與衍生卡片都使用 `_slug(title)` 或 `_slug(source_id)`，並共用 `vault/cards/<id>.md`。沒有 `note-`、`mail-`、`calendar-` 等 namespace，因此人工卡片可能被同名衍生卡片覆蓋。空白或只有標點的標題都會得到 `card` ID。

`add_card()` 採 `load → 修改 → write`；兩個並行請求都讀到舊 index 時，後寫者會覆蓋前寫者的卡片。`rebuild()` 也沒有移除已不再對應來源的舊衍生檔案，可能在磁碟留下過期內容。

### 建議修法

分離 namespace、對 index 更新加鎖，並在重建時只清理受管理的舊卡片。

```python
import hashlib


def _note_id(title: str) -> str:
    normalized = (title or "").strip().lower()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return f"note-{_slug(title)}-{digest}"


def _derived_id(kind: str, source_id: str) -> str:
    return f"{kind}-{_slug(source_id)}"
```

```python
# 實際落檔時，對 index 的讀改寫使用跨執行緒／跨程序鎖，
# 或將 metadata 移至 SQLite transaction。
with index_lock:
    data = load()
    data["cards"] = [c for c in data.get("cards", []) if c["id"] != card["id"]]
    data["cards"].append(card)
    atomic_write(INDEX, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
```

## F-03 — Demo persona seed 未依 mode 隔離，可能污染 live 模式

- **檔案／行號：** `server/persona.py:13-17, 28-29`
- **嚴重度：** High
- **類別：** 正確性、資料隔離

### 說明

`_seed()` 只檢查 `FIXTURE.exists()`，沒有檢查 `accounts.json` 的 `mode`。repository 已內含 demo fixture；因此 live 模式若仍指向此 fixture，便可能把示範身分、角色或寫作習慣混入真人 persona。程式在讀取設定前就決定 seed，mode 判斷順序也不正確。

### 建議修法

先載入設定，只在明確 demo 模式讀取示範 seed；並讓 fixture 路徑與 mode 綁定。

```python
def _seed(cfg: dict) -> dict:
    if (cfg.get("mode") or "demo") != "demo":
        return {}
    if not FIXTURE.exists():
        return {}
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data.get("persona_seed") or {}


cfg = load_cfg()
seed = _seed(cfg)
```

## F-04 — Persona 與 Second Brain 狀態檔可被半寫入或損壞，且讀取失敗會使功能中斷

- **檔案／行號：** `server/persona.py:57-79, 83-86`；`server/second_brain.py:71-78`
- **嚴重度：** High
- **類別：** 錯誤處理、併發、可用性

### 說明

兩處均直接 `write_text()` JSON。讀取端則直接 `json.loads()`，沒有處理空檔、截斷檔或人工修改造成的 `JSONDecodeError`。在寫入、壓力測試或同時 rebuild 時，單一狀態檔損壞即可讓 persona、brain、搜尋或草稿 prompt 功能失效。

### 建議修法

所有狀態檔原子寫入；讀取損壞檔時保留原件、隔離後重建，不應直接覆蓋可能的修正。

```python
def load_json_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        corrupt = path.with_suffix(path.suffix + ".corrupt")
        try:
            path.replace(corrupt)
        except OSError:
            pass
        return {}
```

## F-05 — `@agent` 掃描整封訊息，引用舊信也可能觸發任務

- **檔案／行號：** `server/features/agents.py:40, 88-110, 380-430`
- **嚴重度：** High
- **類別：** 正確性、輸入邊界

### 說明

`MENTION_RE.search(text)` 會搜尋整個 body；文件與 UI 卻描述為「訊息開頭」觸發。轉寄或回覆中只要引用舊信包含 `@agent`，就可能被誤判。kind 推斷又掃描整份 `ask`，引用內容中的「meeting」等字詞也可能改變任務類型。

### 建議修法

先隔離目前回覆層，再要求 mention 位於該層開頭；對引用內容採明確的 quote parser，而不是只移除單行。

```python
MENTION_RE = re.compile(
    r"(?im)^[ \t]*@(agent|research-company|research|prep|meeting)\b"
)


def current_reply_only(text: str) -> str:
    # 實作應辨識常見引用標頭；測試需涵蓋 ">"、"On ... wrote:" 與原始郵件標頭。
    parts = re.split(
        r"(?im)(?=^>+[ \t]*From:|^On .+ wrote:|^[-_]{3,}\s*Original Message)",
        text or "",
        maxsplit=1,
    )
    return parts[0]
```

## F-06 — Overnight 預設會同步，live 帳號下可能非預期連線正式信箱服務

- **檔案／行號：** `scripts/overnight.py:22-26, 67`
- **嚴重度：** High
- **類別：** 正確性、操作安全、相依風險

### 說明

CLI 雖提供 `--no-sync`，但預設傳入 `sync=not args.no_sync`，因此一般執行會同步。當 `accounts.json` 是 live 模式時，這可能連到正式信箱服務，與「本機優先、預設不寄信」不同，也使 CI 或臨時診斷命令具有外部副作用。

### 建議修法

將同步改成明確 opt-in；預設僅使用本機快取。

```python
p.add_argument("--sync", action="store_true", help="explicitly sync configured accounts")
p.add_argument("--no-sync", action="store_true", help=argparse.SUPPRESS)

# 保留相容旗標，但同步必須至少有 --sync。
sync_enabled = args.sync and not args.no_sync
```

## F-07 — 未知 agent driver 被靜默當成本機模式

- **檔案／行號：** `server/features/agents.py:235-252`
- **嚴重度：** Medium
- **類別：** 正確性、錯誤處理

### 說明

`run_task()` 只處理三個遠端 driver；其他值直接落入 `else`，以 local fallback 結束且 `error` 仍為 `None`。設定拼字錯誤會被呈現為正常 fallback，使用者難以察覺 agent 根本沒有執行。

### 建議修法

明列允許值；未知值應回報設定錯誤，再由呼叫端決定是否 fallback。

```python
REMOTE_DRIVERS = {"openai_compatible", "cli", "http"}

if driver == "local":
    used, fallback = "local", True
elif driver in REMOTE_DRIVERS:
    text = agent_bridge.run(pack, cfg).strip()
else:
    raise ValueError("unsupported agent driver")
```

## F-08 — Agent feature 直接依賴 `agent_bridge` 私有函式，绕过統一 dispatcher

- **檔案／行號：** `server/features/agents.py:227-246`
- **嚴重度：** Medium
- **類別：** 可讀性、可測試性、相依風險

### 說明

`_openai()`、`_cli()`、`_http()` 為底層私有名稱。直接呼叫會繞過未來可能集中在 bridge 的 timeout、usage accounting、redaction、driver fallback 與錯誤標準化，也讓單元測試必須 patch 私有函式。

### 建議修法

在 bridge 提供單一公開介面，feature 不得 import 底層 driver。

```python
# agent_bridge.py
def run(pack: dict, cfg: dict) -> tuple[str, dict]:
    """Execute the configured driver and normalize result, usage, and errors."""
    ...


# features/agents.py
text, metadata = agent_bridge.run(pack, cfg)
```

## F-09 — 前端 fetch 未統一檢查 status 與 response type

- **檔案／行號：** `ui/modules/agents.js:40-47`；Markdown 預覽區約 `201-251`
- **嚴重度：** Medium
- **類別：** 錯誤處理

### 說明

`getJSON()` 直接呼叫 `.json()`，`postJSON()` 也假設所有回應皆為 JSON。500 的 HTML 錯誤頁會變成不明 JSON exception；Markdown 預覽則未檢查 `response.ok`，可能把 404 HTML 當 Markdown 顯示。

### 建議修法

提供單一 fetch helper，限制 response 大小、加入 timeout，並保留不含敏感內容的錯誤碼。

```javascript
async function request(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(path, { ...options, signal: controller.signal });
    const body = await response.text();
    if (!response.ok) {
      const error = new Error(`HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    try {
      return JSON.parse(body);
    } catch {
      throw new Error("Invalid JSON response");
    }
  } finally {
    clearTimeout(timer);
  }
}
```

## F-10 — Markdown 預覽存在 stale response race

- **檔案／行號：** `ui/modules/agents.js:201-251`
- **嚴重度：** Medium
- **類別：** 併發、正確性

### 說明

預覽切換 A → B 時，A 的較慢回應可能在 B 的 `tagMd` 元素建立後才完成，因而把 A 的內容寫入 B 的預覽。程式沒有 request token 或 abort controller。

### 建議修法

每次預覽遞增 token，並在 response 寫入 DOM 前確認仍是目前預覽。

```javascript
view.previewToken = (view.previewToken || 0) + 1;
const token = view.previewToken;
const response = await fetch(url);
const markdown = await response.text();
if (token !== view.previewToken || view.preview?.id !== id) return;
const element = document.getElementById("tagMd");
if (element) element.textContent = markdown;
```

## F-11 — Overnight 數量參數允許負數與無上限值

- **檔案／行號：** `scripts/overnight.py:28, 31, 67`
- **嚴重度：** Medium
- **類別：** 輸入驗證、可測試性

### 說明

`--max-drafts` 與 `--sync-limit` 接受負數，也沒有合理上限。負值可能導致非預期的 range 行為或繞過預期限制；極大值則可能造成長時間執行與資源耗盡。

### 建議修法

在 argparse 層限制非負與合理上限。

```python
def bounded_int(lower: int, upper: int):
    def parse(value: str) -> int:
        number = int(value)
        if not lower <= number <= upper:
            raise argparse.ArgumentTypeError(f"expected {lower}..{upper}")
        return number
    return parse


p.add_argument("--max-drafts", type=bounded_int(0, 100), default=10)
p.add_argument("--sync-limit", type=bounded_int(0, 1000), default=25)
```

## F-12 — 本機敏感資料與設定檔缺少明確權限收斂

- **檔案／行號：** `install.sh:18-20`；`run.sh:1-8`；`server/features/agents.py:328-331`；`server/persona.py:56-79`；`server/second_brain.py:20-32, 71, 107`
- **嚴重度：** Medium
- **類別：** 安全、部署相依

### 說明

`data/`、`vault/`、帳號設定與 deliverable 會包含郵件摘要、人格與來源內容。Git ignore 只能避免部分提交，不能防止同機其他帳號讀取。`run.sh` 的 process umask 也未固定。

### 建議修法

安裝與執行時使用 restrictive umask，既有敏感檔案建立後再收斂權限。

```bash
umask 077
mkdir -p -m 700 data vault vault/cards
[[ -f accounts.json ]] || cp accounts.example.json accounts.json
[[ -f agent.json ]] || cp agent.example.json agent.json
chmod 600 accounts.json agent.json 2>/dev/null || true
```

## F-13 — `.gitignore` 只忽略部分 vault 產物，其他本機檔案可能被誤提交

- **檔案／行號：** `.gitignore:11-16`
- **嚴重度：** Medium
- **類別：** 安全、可維護性

### 說明

目前只忽略 `vault/persona.*`、`vault/index.json` 與 `vault/cards/*.md`。若日後使用 JSON、HTML、附件、匯出檔或巢狀卡片，會不會被 Git 忽略取決�副檔名，存在誤提交風險。

### 建議修法

預設忽略整個 vault，僅明確保留 `.gitkeep`；如需模板，應另設受控的 template 目錄。

```gitignore
vault/**
!vault/cards/
vault/cards/*
!vault/cards/.gitkeep
```

## F-14 — Smoke script 以正規式模擬 YAML workflow，結構改變時可能靜默誤測

- **檔案／行號：** `scripts/smoke.sh:103-161`
- **嚴重度：** Medium
- **類別：** 測試可靠性、相依風險

### 說明

腳本自行解析 `.github/workflows/smoke.yml` 的 `run:` 區塊，只支援有限格式。workflow 一旦加入 YAML anchor、環境矩陣、不同縮排、shell block 或 reusable workflow，解析器可能漏掉步驟或執行不同語意，卻仍回報成功。

### 建議修法

不要在 shell script 內複製 workflow 語意。讓 workflow 只呼叫一個明確的 smoke entry point，由腳本維護固定步驟；或者 parser 遇到未知結構時必須 fail closed。

```bash
# 未來 CI 結構應由單一入口維護；此處只顯示契約。
if ! bash scripts/smoke.sh; then
  echo "smoke: failed" >&2
  exit 1
fi
```

## F-15 — Smoke scratch copy 會跟隨 symlink，且多背景程序的清理只追蹤最後 PID

- **檔案／行號：** `scripts/smoke.sh:64-100, 164-193`
- **嚴重度：** Medium
- **類別：** 測試隔離、資源管理

### 說明

複製檔案時 `isfile()` 與 `copy2()` 會跟隨 symlink；repo 中若存在指向外部路徑的 tracked symlink，scratch test 可能讀取 repo 外內容。cleanup 只保存單一 `SERVER_PID`；若 workflow 增加多個背景程序，先前程序可能未被終止。

### 建議修法

先由 Git index 檢查 mode `120000` 並 fail closed；背景 PID 使用陣列管理。

```python
# 追蹤 Git mode；120000 代表 symlink，測試副本不得跟隨。
tracked = subprocess.run(
    ["git", "-C", src, "ls-files", "-s", "-z"],
    check=True,
    capture_output=True,
).stdout
if any(entry.startswith(b"120000 ") for entry in tracked.split(b"\0") if entry):
    raise SystemExit("smoke: tracked symlinks are not allowed in scratch copies")
```

```bash
SERVER_PIDS=()
cleanup() {
  local pid
  for pid in "${SERVER_PIDS[@]:-}"; do
    [[ -n "$pid" ]] && kill -TERM -- "-$pid" 2>/dev/null || true
  done
}
```

## F-16 — ICS fixture 使用不一致且未宣告的 TZID

- **檔案／行號：** `fixtures/ics/lee-example.ics:8-9, 16-17`
- **嚴重度：** Medium
- **類別：** 正確性、相容性

### 說明

同一檔案先使用 `TZID=Taipei Standard Time`，後續事件使用 `TZID=Asia/Taipei`，但都沒有 `VTIMEZONE`。部分 ICS parser 會依 IANA 名稱處理，部分只認 registry 名稱或要求對應 VTIMEZONE，造成時區 fallback 或事件時間偏移。

### 建議修法

統一使用 IANA `Asia/Taipei` 並補完整 `VTIMEZONE`；測試應驗證 DST／固定 offset 與 round-trip。

```text
BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VTIMEZONE
TZID:Asia/Taipei
BEGIN:STANDARD
DTSTART:19700101T000000
TZOFFSETFROM:+0800
TZOFFSETTO:+0800
TZNAME:Taipei
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:FAKE_VALUE_FOR_TEST
DTSTAMP:20260901T000000Z
DTSTART;TZID=Asia/Taipei:20260831T120000
DTEND;TZID=Asia/Taipei:20260831T130000
END:VEVENT
END:VCALENDAR
```

## F-17 — Deliverable 讀取存在 TOCTOU，且未捕捉 `OSError`

- **檔案／行號：** `server/features/agents.py:351-358`
- **嚴重度：** Medium
- **類別：** 錯誤處理、併發

### 說明

`is_file()` 與 `read_bytes()` 分成兩步；檔案可能在兩者之間被刪除或替換。此例外未轉為 404，會形成 generic 500。原子寫入完成後可降低機率，但讀取端仍應自行處理競態。

### 建議修法

直接開啟並捕捉 `FileNotFoundError`／`OSError`，不要以預檢作為存在性保證。

```python
def read_deliverable(did: str, fmt: str = "md") -> tuple[bytes, str] | None:
    if not _valid_id(did) or fmt not in {"md", "html", "json"}:
        return None
    try:
        body = (DELIV_DIR / f"{did}.{fmt}").read_bytes()
    except (FileNotFoundError, OSError):
        return None
    ctype = {
        "md": "text/markdown; charset=utf-8",
        "html": "text/html; charset=utf-8",
        "json": "application/json; charset=utf-8",
    }[fmt]
    return body, ctype
```

## F-18 — 外部 agent driver 的信任邊界與 timeout 契約不明

- **檔案／行號：** `agent.example.json:2-17`；`adapters/README.md:9-15, 30-46`；`adapters/README.zh-Hant.md:9-15, 30-46`
- **嚴重度：** Medium
- **類別：** 相依風險、安全、錯誤處理

### 說明

CLI 可執行任意 argv，HTTP/OpenAI-compatible endpoint 可指向任一網址。文件沒有說明：

- 是否繼承完整 process environment；
- CLI 是否使用 shell、工作目錄與檔案系統權限；
- endpoint timeout、redirect、credential URL 與 response size 上限；
- local fallback 是否只在允許的錯誤上發生。

由於 `server/agent_bridge.py` 內容未提供，本項列為「契約風險，需內容級確認」，不是已確認的 RCE。

### 建議修法

建立允許的 driver 設定 schema；CLI 固定 `shell=False`、清理環境、使用受限工作目錄；HTTP 驗證 URL、禁止 embedded credential、限制 redirect 與 response size。

```python
from urllib.parse import urlparse


def validate_http_endpoint(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("unsupported endpoint scheme")
    if parsed.username or parsed.password:
        raise ValueError("credentials must not be embedded in endpoint URL")
    return url
```

## F-19 — 缺少針對本次高風險邊界的回歸測試契約

- **檔案／行號：** `tests/test_tpi_agents_core.py`、`tests/test_tpi_agents_mention.py`、`tests/test_tpi_brain_profile.py`、`tests/test_tpi_brain_fix.py`、`tests/test_tpi_foundation_cache.py`；本次快照未提供其內容
- **嚴重度：** Medium
- **類別：** 可測試性

### 說明

由檔名可確認已有 agents、brain、cache 等測試群，但無法確認是否涵蓋：

- deliverable 寫入中途失敗；
- 同時寫入兩個不同卡片；
- persona JSON 損壞；
- 相同標題的人工卡片與衍生卡片；
- quoted `@agent`；
- 未支援 driver；
- overnight 預設不得同步；
- ICS 缺 VTIMEZONE。

### 建議修法

加入下表測試矩陣，全部使用暫存目錄與假資料，不連外部服務。

```python
import tempfile
from pathlib import Path


def test_quoted_mention_does_not_trigger():
    text = "> On an earlier message, someone wrote @agent please research\ncurrent reply"
    assert parse_mention(text) is None


def test_unknown_driver_is_reported():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert root.is_dir()


def test_note_and_derived_ids_do_not_collide():
    assert _note_id("same title") != _derived_id("mail", "same title")
```

## F-20 — Deliverable HTML 產生非法的獨立 `<li>` 元素

- **檔案／行號：** `server/features/agents.py:280-295`
- **嚴重度：** Low
- **類別：** 正確性、可讀性

### 說明

每個 Markdown list item 都直接輸出 `<li>`，但沒有 `<ul>`／`<ol>` 包覆。這不是合法 HTML list，瀏覽器雖常能修正呈現，但螢幕閱讀器、DOM 測試與輸出格式會不一致。

### 建議修法

最簡單可改成 `<div class="item">`；若要保留 list semantic，應收集相鄰項目後包成 `<ul>`。

```python
paras.append(f'<div class="item">• {esc(s.lstrip()[2:])}</div>')
```

## F-21 — 可讀性與設定檔有可清理的小型冗餘

- **檔案／行號：** `.gitignore:19-20`；`server/persona.py:6`；`server/second_brain.py:6`
- **嚴重度：** Low
- **類別：** 可讀性

### 說明

`.gitignore` 重複列出相同目錄；兩個 Python 模組匯入未使用的 `Path`。這些不影響功能，但會增加噪音並掩蓋真正的設定差異。

### 建議修法

刪除重複行與未使用 import，並以 lint 規則防止再次出現。

## F-22 — 狀態文件包含環境相關敘述，需避免與程式能力漂移

- **檔案／行號：** `STATE.md:5-13, 69-104`；`state/tpi-*.md` 各檔 `status`、`next`、`log`
- **嚴重度：** Low
- **類別：** 可讀性、文件正確性

### 說明

`STATE.md` 與各 work-package 狀態檔同時記錄功能完成度、測試數量、環境路徑與歷史結果。這些內容由不同流程產生，容易與實際程式或測試結果漂移；環境專屬路徑也不應成為長期公開文件的一部分。

### 建議修法

保留功能矩陣與穩定 release note；把机器／執行環境路徑改成一般描述，並由 CI 自動核對 feature、route 與測試清單。

```markdown
status: done
verification:
  - unittest: required
  - smoke: required
  - live_services_contacted: false
```
