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
    { "email": "you@gmail.com", "platform": "gmail", "driver": "gog", "label": "工作" }
  ]
}
```

- `gog`：Gmail，走 [gog](https://gogcli.sh)
- `gsk`：額外 IMAP／Outlook，只走 Genspark CLI 的信件 API；TooPowerInbox 不呼叫 Super Agent

然後在面板按「重新整理」。

## 目錄

```
server/yhbmail.py      信件、分類、SQLite
server/persona.py      更了解你
server/second_brain.py 大腦卡片
server/agent_bridge.py 自帶 Agent 與工具
server/app.py          HTTP 與面板
ui/index.html          可視化面板（繁中／英文）
skills/                晨間簡報、快速補課等
vault/                 人格與卡片（本機，不進 git）
```

## 授權

MIT。見 [LICENSE](LICENSE)。
