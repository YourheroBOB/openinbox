# Bring your own agent

[正體中文](README.zh-Hant.md) · English

TooPowerInbox never ships a hosted model. The dashboard runs a local heuristic by default. Point `agent.json` at whatever you already pay for.

## Drivers

| `driver` | What it calls |
|---|---|
| `local` | Built-in triage. Zero network. Always available as fallback. |
| `openai_compatible` | `POST {base_url}/chat/completions` (OpenAI, Ollama, vLLM, LiteLLM…) |
| `cli` | Your argv. The context pack is written to stdin. |
| `http` | `POST` the context pack to your worker. Return `{ "answer": "…" }`. |

Copy `agent.example.json` to `agent.json` (the installer already does this).

### Ollama

```json
{
  "driver": "openai_compatible",
  "openai_compatible": {
    "base_url": "http://127.0.0.1:11434/v1",
    "model": "llama3.1",
    "api_key_env": "OPENAI_API_KEY",
    "allow_private": true
  }
}
```

### Claude CLI / Codex / any stdin agent

```json
{
  "driver": "cli",
  "cli": { "command": ["claude", "-p"], "timeout_sec": 180 }
}
```

### Your own loop

1. `GET /api/v1/context` for persona + board + recent mail.
2. Call tools with `POST /api/v1/tools/{name}`.
3. Optionally `POST /api/v1/agent/run` if you still want the built-in wrapper.

Tools: `list_inbox`, `brain_board`, `search_brain`, `persona`, `save_draft`.

Send is not exposed. Drafts stay in the local SQLite file.

### CLI driver and permissions

The `cli` driver writes the full context pack (including mail snippets) to your command's stdin. If that command has its own file or network tools, those run with **that command's** privileges—TooPowerInbox does not sandbox them further.
