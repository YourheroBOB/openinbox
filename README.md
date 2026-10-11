# TooPowerInbox

[正體中文](README.zh-Hant.md) · English

Local email brain you can actually own. One process, no hosted model, no credit meter.

A visualization dashboard, a Second Brain vault, a know-you-better persona, and a tool API so **you bring the agent**. The panel ships in Traditional Chinese and English.

```
./install.sh && ./run.sh
```

Opens [http://127.0.0.1:8770/](http://127.0.0.1:8770/). Demo mail loads on the first boot. Python 3.9+, zero pip packages. Switch language with 繁中 / EN, or `?lang=zh-Hant` / `?lang=en`.

## What you get

1. **Inbox client**: three-pane mail UI with five-bucket triage tabs and counts, keyboard navigation (`j`/`k`/`Enter`, `/` to search, `c` for Copilot), read/unread, markdown rendering, deep links (`#thread=…`, `#copilot=1`).
2. **Copilot drawer**: a GenMAIL-style side chat over your inbox — 30-second summary, action/deadline extraction, and three reply drafts (quick ack / full / decline) per email, with one-click save into local drafts. Runs on your BYO agent; falls back to local heuristics with a clear banner when no LLM is wired.
3. **Second Brain**: durable markdown cards in `vault/cards`, rebuilt from mail and calendar.
4. **Know you better**: writing habits, inbox rules, attention, top senders (`vault/persona.md`).
5. **`yhbmail.py`**: connectors + classifier + local cache. The mail spine.
6. **BYO agent**: `local` / OpenAI-compatible / CLI / HTTP. See [adapters/README.md](adapters/README.md).

This is an architecture clone of the “email brain + unified inbox + agent” idea, not a pixel copy of any commercial client. Not affiliated with GenSpark, Super App, or any vendor mail product. Send is off. Drafts never leave the machine unless you wire that yourself.

## Talk to it from any agent

```http
GET  /api/v1/tools
GET  /api/v1/context?lang=zh-Hant
POST /api/v1/tools/list_inbox
POST /api/v1/agent/run
{"ask":"今天什麼要我處理？","skill":"morning-brief","lang":"zh-Hant"}
POST /api/copilot
{"mode":"summarize|todos|draft|chat","item_id":"…","ask":"…","lang":"zh-Hant"}
```

Drop extra skills as `skills/*.md`. The local driver and any CLI/HTTP worker both receive the skill text in the context pack.

## Real mail (optional)

Demo mode is the default. When you want live boxes, edit `accounts.json`:

```json
{
  "mode": "live",
  "accounts": [
    { "email": "you@example.com", "platform": "gmail", "driver": "gog", "label": "Work" }
  ]
}
```

- `gog`: Gmail via [gog](https://gogcli.sh)
- `gsk`: extra IMAP/Outlook transport through Genspark CLI (mail API only; TooPowerInbox does not call Super Agent)

Then press **Refresh** in the dashboard.

To wipe what this machine has cached (mail, events, Copilot history, derived cards), use **Clear local cache** in the sidebar or `POST /api/cache/clear` (`{"reseed": true}` reloads the demo mail). Drafts and the note cards you wrote stay. `GET /api/cache` shows what is cached.

## Run on a cloud Linux host

The server only listens on `127.0.0.1:8770`, so on a remote box you reach it through an SSH tunnel. No public port, no reverse proxy, no deploy config.

On the host:

```bash
git clone https://github.com/YourheroBOB/openinbox.git && cd openinbox
./install.sh
OPENINBOX_NO_BROWSER=1 ./run.sh        # keep it alive with tmux / screen if you like
```

On your laptop:

```bash
ssh -N -L 8770:127.0.0.1:8770 user@your-host.example.com
```

Then open [http://127.0.0.1:8770/](http://127.0.0.1:8770/) locally. If 8770 is taken on the laptop, use `-L 8771:127.0.0.1:8770` and open port 8771. Keep the host firewall closed for 8770; the tunnel is the only way in. `accounts.json`, `agent.json`, `data/` and `vault/` live on the host, so treat its disk like your inbox.

## Add a feature

Drop `server/features/<name>.py`; its routes register themselves, `server/app.py` does not change:

```python
from features import get, post

@get("/api/hello")
def hello(req):            # req.query, req.body, req.lang_zh()
    return {"hello": "world"}
```

UI goes in `ui/modules/<name>.js`; `index.html` loads every module listed by `GET /api/ui-modules`. Ship each UI string in both `zh` and `en`. `GET /api/features` lists loaded features, routes and import errors.

## Tests

```bash
python3 -m unittest discover -s tests   # stdlib unittest, throwaway data dir
scripts/smoke.sh                        # the CI smoke workflow, run locally on Linux
```

## Layout

```
server/yhbmail.py      mail, taxonomy, SQLite
server/persona.py      know you better
server/second_brain.py vault cards
server/agent_bridge.py BYO agent + tools
server/app.py          HTTP + dashboard
server/features/       plug-in routes (cache, plugins, …)
ui/index.html          visualization panel (zh-Hant / en)
ui/modules/            plug-in UI scripts
skills/                morning-brief, catch-me-up, …
tests/                 unittest suite
scripts/smoke.sh       local smoke run
vault/                 persona + cards (local, gitignored)
```

## License

MIT. See [LICENSE](LICENSE).
