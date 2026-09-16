# Contributing

OpenInbox stays small on purpose.

- Python 3.9 stdlib only in `server/`. No pip unless the change is an optional adapter.
- Do not add a hosted model, telemetry, or a send path that fires without an explicit local flag.
- Keep demo fixtures fictional. No real inboxes in the repo.
- New skills are markdown in `skills/`. New tools belong in `agent_bridge.TOOLS` and `invoke_tool`.

```
./install.sh && OPENINBOX_NO_BROWSER=1 ./run.sh
curl -s http://127.0.0.1:8770/api/health
```
