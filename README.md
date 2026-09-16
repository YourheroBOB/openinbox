# TooPowerInbox

[正體中文](README.zh-Hant.md) · English

Local email brain you can actually own. One process, no hosted model, no credit meter.

A visualization dashboard, a Second Brain vault, a know-you-better persona, and a tool API so **you bring the agent**. The panel ships in Traditional Chinese and English.

```
./install.sh && ./run.sh
```

Opens [http://127.0.0.1:8770/](http://127.0.0.1:8770/). Demo mail loads on the first boot. Python 3.9+, zero pip packages. Switch language with 繁中 / EN, or `?lang=zh-Hant` / `?lang=en`.

## What you get

1. **Dashboard**: five-bucket triage (Needs you / Upcoming / Worth a look / FYI / Cleanup) with live bars.
2. **Second Brain**: durable markdown cards in `vault/cards`, rebuilt from mail and calendar.
3. **Know you better**: writing habits, inbox rules, attention, top senders (`vault/persona.md`).
4. **`yhbmail.py`**: connectors + classifier + local cache. The mail spine.
5. **BYO agent**: `local` / OpenAI-compatible / CLI / HTTP. See [adapters/README.md](adapters/README.md).

This is an architecture clone of the “email brain + unified inbox + agent” idea, not a pixel copy of any commercial client. Not affiliated with GenSpark, Super App, or any vendor mail product. Send is off. Drafts never leave the machine unless you wire that yourself.

## Talk to it from any agent

```http
GET  /api/v1/tools
GET  /api/v1/context?lang=zh-Hant
POST /api/v1/tools/list_inbox
POST /api/v1/agent/run
{"ask":"今天什麼要我處理？","skill":"morning-brief","lang":"zh-Hant"}
```

Drop extra skills as `skills/*.md`. The local driver and any CLI/HTTP worker both receive the skill text in the context pack.

## Real mail (optional)

Demo mode is the default. When you want live boxes, edit `accounts.json`:

```json
{
  "mode": "live",
  "accounts": [
    { "email": "you@gmail.com", "platform": "gmail", "driver": "gog", "label": "Work" }
  ]
}
```

- `gog`: Gmail via [gog](https://gogcli.sh)
- `gsk`: extra IMAP/Outlook transport through Genspark CLI (mail API only; TooPowerInbox does not call Super Agent)

Then press **Refresh** in the dashboard.

## Layout

```
server/yhbmail.py      mail, taxonomy, SQLite
server/persona.py      know you better
server/second_brain.py vault cards
server/agent_bridge.py BYO agent + tools
server/app.py          HTTP + dashboard
ui/index.html          visualization panel (zh-Hant / en)
skills/                morning-brief, catch-me-up, …
vault/                 persona + cards (local, gitignored)
```

## License

MIT. See [LICENSE](LICENSE).
