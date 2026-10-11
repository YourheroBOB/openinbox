# TooPowerInbox

[English](README.md) · 正體中文

本機信箱腦，真正屬於你。一支行程，沒有託管模型，沒有點數表。

可視化面板、第二大腦、更了解你、再加上工具 API，**Agent 由你自己帶進來**。面板內建正體中文與英文。

```
./install.sh && ./run.sh
```

會打開 [http://127.0.0.1:8770/](http://127.0.0.1:8770/)。第一次開機載入示範信件。Python 3.9 以上，不用 pip。左側按 繁中 / EN，或用 `?lang=zh-Hant` / `?lang=en`。

## 你會拿到什麼

1. **郵件客戶端**：三欄式收件匣，五桶分類籤即時計數、鍵盤導航（`j`／`k`／`Enter`，`/` 搜尋，`c` 開 Copilot）、已讀切換、Markdown 內文渲染、深連結（`#thread=…`、`#copilot=1`）。
2. **Copilot 抽屜**：GenMAIL 式右側對話抽屜——30 秒摘要、待辦與期限萃取、一鍵三版回信草稿（快速確認／完整回覆／婉拒），存進本機草稿匣。跑在你自帶的 Agent 上；沒接 LLM 時自動降級本機啟發式並明確標示。
3. **第二大腦**：`vault/cards` 裡的 markdown 卡，從信件與行事曆蒸餾。
4. **更了解你**：文風、收信習慣、此刻要注意、常出現的寄件人（`vault/persona.md`）。
5. **`yhbmail.py`**：接線、分類、本機快取。信箱脊。
6. **自帶 Agent**：`local`／OpenAI 相容／CLI／HTTP。見 [adapters/README.md](adapters/README.md) 與 [adapters/README.zh-Hant.md](adapters/README.zh-Hant.md)。

這是「信箱腦＋統一收件匣＋Agent」的架構實作，不是任何商業客戶端的畫面拷貝。與 GenSpark、Super App 或任何廠商郵件產品無關。預設不寄信。草稿不會離開這台機器，除非你自己接出去。

## 讓任何 Agent 來叫它

```http
GET  /api/v1/tools
GET  /api/v1/context?lang=zh-Hant
POST /api/v1/tools/list_inbox
POST /api/v1/agent/run
{"ask":"今天什麼要我處理？","skill":"morning-brief","lang":"zh-Hant"}
POST /api/copilot
{"mode":"summarize|todos|draft|chat","item_id":"…","ask":"…","lang":"zh-Hant"}
```

額外技能就丟 `skills/*.md`。本機驅動與 CLI／HTTP worker 都會在 context pack 裡拿到技能本文。

## 真信箱（可選）

預設是示範模式。要接真信箱就改 `accounts.json`：

```json
{
  "mode": "live",
  "accounts": [
    { "email": "you@example.com", "platform": "gmail", "driver": "gog", "label": "工作" },
    { "email": "me@example.com", "driver": "imap", "provider": "icloud", "label": "iCloud",
      "password_env": "TPI_IMAP_ICLOUD_PASSWORD" }
  ]
}
```

- `gog`：Gmail，走 [gog](https://gogcli.sh)
- `gsk`：額外 IMAP／Outlook，只走 Genspark CLI 的信件 API；TooPowerInbox 不呼叫 Super Agent
- `imap`：唯讀 IMAP（標準函式庫 `imaplib`）。`provider` 可填 `icloud`、`fastmail`、`yahoo`、`zoho`，其他信箱改填 `host`／`port`（預設 993 SSL；`security` 可為 `starttls`，`none` 只限本機 loopback）。另可設 `username`、`mailbox`（預設 `INBOX`）。以 EXAMINE 開信箱、BODY.PEEK 抓信，伺服器上什麼都不改，連「已讀」都不會標。

IMAP 密碼只從環境變數讀：`password_env` 指定的變數，沒填就讀 `TPI_IMAP_PASSWORD_<信箱大寫、非英數換成 _>`。`accounts.json` 裡放明文 `password` 會被拒絕。iCloud 要用 Apple ID 的 App 專用密碼。

```bash
export TPI_IMAP_ICLOUD_PASSWORD='…'   # 不要寫進任何檔案
./run.sh
```

所有帳號同步進同一個收件匣，每封信都標上帳號；左側「信箱」可依帳號篩選，顯示未讀數、驅動類型、缺密碼或上次同步錯誤，IMAP 帳號有「測試連線」（`POST /api/providers/check`，只登入＋EXAMINE）。`GET /api/providers` 列出帳號、各帳號信件數與上次同步結果，只回環境變數名稱，不回密碼。

然後在面板按「重新整理」。

要清掉這台機器上的快取（信件、行程、Copilot 紀錄、衍生卡片），按左側「清除本機快取」，或 `POST /api/cache/clear`（帶 `{"reseed": true}` 會重新載入示範信）。草稿與你自己寫的筆記卡保留。`GET /api/cache` 可看目前快取了什麼。

## 在雲端 Linux 主機執行

伺服器只聽 `127.0.0.1:8770`，所以在遠端主機上要用 SSH 通道連進去。不開對外埠、不架反向代理、不寫任何部署設定。

在主機上：

```bash
git clone https://github.com/YourheroBOB/openinbox.git && cd openinbox
./install.sh
OPENINBOX_NO_BROWSER=1 ./run.sh        # 想常駐就放進 tmux／screen
```

在你的筆電上：

```bash
ssh -N -L 8770:127.0.0.1:8770 user@your-host.example.com
```

然後在本機打開 [http://127.0.0.1:8770/](http://127.0.0.1:8770/)。筆電的 8770 被占用時，改用 `-L 8771:127.0.0.1:8770` 再開 8771。主機防火牆不要放行 8770，通道是唯一入口。`accounts.json`、`agent.json`、`data/`、`vault/` 都在主機上，那顆硬碟請當成你的信箱來保護。

## 加功能

放一支 `server/features/<名稱>.py`，路由會自動註冊，不必改 `server/app.py`：

```python
from features import get, post

@get("/api/hello")
def hello(req):            # req.query、req.body、req.lang_zh()
    return {"hello": "world"}
```

介面放 `ui/modules/<名稱>.js`；`index.html` 會載入 `GET /api/ui-modules` 列出的每個模組。每個介面字串都要有 `zh` 與 `en`。`GET /api/features` 列出已載入的功能、路由與載入錯誤。

## 測試

```bash
python3 -m unittest discover -s tests   # 標準函式庫 unittest，用拋棄式資料夾
scripts/smoke.sh                        # 在 Linux 本機跑 CI 的 smoke 檢查
```

## 目錄

```
server/yhbmail.py      信件、分類、SQLite
server/persona.py      更了解你
server/second_brain.py 大腦卡片
server/agent_bridge.py 自帶 Agent 與工具
server/app.py          HTTP 與面板
server/features/       外掛路由（cache、plugins…）
ui/index.html          可視化面板（繁中／英文）
ui/modules/            外掛介面腳本
skills/                晨間簡報、快速補課等
tests/                 unittest 測試
scripts/smoke.sh       本機 smoke 檢查
vault/                 人格與卡片（本機，不進 git）
```

## 授權

MIT。見 [LICENSE](LICENSE)。
