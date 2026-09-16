# Contributing

[正體中文](CONTRIBUTING.zh-Hant.md) · English

TooPowerInbox stays small on purpose.

- Python 3.9 stdlib only in `server/`. No pip unless the change is an optional adapter.
- Do not add a hosted model, telemetry, or a send path that fires without an explicit local flag.
- Keep demo fixtures fictional. No real inboxes in the repo.
- New skills are bilingual markdown in `skills/` (Traditional Chinese first, then English).
- New tools belong in `agent_bridge.TOOLS` and `invoke_tool`.
- UI strings go in both `zh-Hant` and `en` in `ui/index.html`. No simplified Chinese.

```
./install.sh && OPENINBOX_NO_BROWSER=1 ./run.sh
curl -s http://127.0.0.1:8770/api/health
```
