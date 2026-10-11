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
7. **Skills** (sidebar ✦ Skills, `GET /api/skills`, `POST /api/skills/run`): Morning Brief, Catch Me Up, Organize Inbox, Find It For Me, Meeting Prep, Brief this person, Turn into a slide (self-contained HTML deck in `data/slides/`), CRM this contact (local CRM in `data/contacts.json`, `GET /api/contacts`). Each has an on/off switch (`POST /api/skills/settings`, stored in `data/skills.json`); a switched-off skill refuses to run. Results are computed locally and rewritten by your BYO agent when one is wired.
8. **BYOK usage** (sidebar 📊 Usage, `GET /api/usage`): every call to your own model appends token counts to `data/usage.jsonl` (exact when the endpoint returns `usage`, estimated otherwise). No prompts, answers or keys are logged.

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

## MCP server (Claude Desktop, Cursor, any MCP client)

`server/mcp_server.py` speaks MCP over stdio (JSON-RPC 2.0, one message per line: `initialize`, `tools/list`, `tools/call`, `ping`). It exposes the same five tools as the HTTP API: `list_inbox`, `brain_board`, `search_brain`, `persona`, `save_draft`. Everything is read from the local cache; `save_draft` only writes a row to the local SQLite drafts table and never sends. No network, no pip packages. The web app does not need to be running.

Claude Desktop (`claude_desktop_config.json`) and Cursor (`~/.cursor/mcp.json` or `.cursor/mcp.json` in a project) use the same block. Replace `/path/to/openinbox` with your checkout:

```json
{
  "mcpServers": {
    "toopowerinbox": {
      "command": "python3",
      "args": ["/path/to/openinbox/server/mcp_server.py"],
      "env": { "OPENINBOX_ROOT": "/path/to/openinbox" }
    }
  }
}
```

`OPENINBOX_ROOT` is optional (defaults to the checkout). In demo mode the server seeds `fixtures/` on start. Quick check from a shell:

```
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{}}}' '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | python3 server/mcp_server.py
```

## Real mail (optional)

Demo mode is the default. When you want live boxes, edit `accounts.json`:

```json
{
  "mode": "live",
  "accounts": [
    { "email": "you@example.com", "platform": "gmail", "driver": "gog", "label": "Work" },
    { "email": "me@example.com", "driver": "imap", "provider": "icloud", "label": "iCloud",
      "password_env": "TPI_IMAP_ICLOUD_PASSWORD" }
  ]
}
```

- `gog`: Gmail via [gog](https://gogcli.sh)
- `gsk`: extra IMAP/Outlook transport through Genspark CLI (mail API only; TooPowerInbox does not call Super Agent)
- `imap`: read-only IMAP (stdlib `imaplib`). `provider` can be `icloud`, `fastmail`, `yahoo` or `zoho`; for anything else set `host` / `port` (default 993 over SSL; `security` may be `starttls`, and `none` is allowed only on a loopback host). Optional: `username`, `mailbox` (default `INBOX`). The mailbox is opened with EXAMINE and fetched with BODY.PEEK, so nothing on the server changes, not even the read flag.

IMAP passwords come only from the environment: the variable named by `password_env`, or `TPI_IMAP_PASSWORD_<EMAIL upper-cased, non-alphanumerics as _>`. A plaintext `password` in `accounts.json` is refused. iCloud needs an app-specific password for your Apple ID.

```bash
export TPI_IMAP_ICLOUD_PASSWORD='…'   # never write it into a file
./run.sh
```

Every account syncs into one inbox and each message is tagged with its account. The sidebar **Accounts** list filters by account and shows unread counts, the driver, a missing-password hint or the last sync error; IMAP accounts get **Test connection** (`POST /api/providers/check`, login + EXAMINE only). `GET /api/providers` lists accounts with per-account counts and last sync result; it returns env var names, never passwords.

Then press **Refresh** in the dashboard.

To wipe what this machine has cached (mail, events, Copilot history, derived cards), use **Clear local cache** in the sidebar or `POST /api/cache/clear` (`{"reseed": true}` reloads the demo mail). Drafts and the note cards you wrote stay. `GET /api/cache` shows what is cached. Calendar data you created or imported also stays: local / AI-booked events, invite drafts and imported colleague ICS feeds (`cal_feeds`). Remove a colleague feed with its delete button in the calendar's free/busy panel or `POST /api/cal/feed/delete` (`{"id": N}`).

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

## Install as an app (Mac, Windows, iOS, Android)

TooPowerInbox is an installable PWA, so there is no separate native app to download.

- **Chrome / Edge on Mac, Windows, Linux, Android**: open [http://127.0.0.1:8770/](http://127.0.0.1:8770/) and press **📲 Install app** in the sidebar (or the install icon in the address bar).
- **iPhone / iPad**: in Safari tap **Share → Add to Home Screen**.

Below 760 px wide the panel switches to a phone layout: a bottom tab bar (Mail, Calendar, Drafts, Copilot, Menu), the sidebar as a slide-in drawer, and the message or Copilot as a full screen that the back gesture closes. Home-screen shortcuts jump straight to Mail, Calendar, Drafts or Copilot.

Service workers need HTTPS or `127.0.0.1`. On a phone, forward the port with an SSH client app (the same `ssh -N -L 8770:127.0.0.1:8770 …` as above) and open `http://127.0.0.1:8770/`; the server still listens on loopback only. The service worker (`/sw.js`) caches only static files: the offline page, the manifest, icons and `ui/modules/*.js`. It never touches `/api/*`, so no mail is stored in the browser. When the server can't be reached the app shows an offline page with a retry button. `GET /api/mobile/info` lists exactly what is cached.

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
server/mcp_server.py   MCP server (stdio)
server/app.py          HTTP + dashboard
server/features/       plug-in routes (cache, plugins, imap, providers, …)
ui/index.html          visualization panel (zh-Hant / en)
ui/modules/            plug-in UI scripts
ui/pwa/                service worker + offline page (served by server/features/mobile.py)
skills/                morning-brief, catch-me-up, …
tests/                 unittest suite
scripts/smoke.sh       local smoke run
vault/                 persona + cards (local, gitignored)
```

## License

MIT. See [LICENSE](LICENSE).
