# 自己帶 Agent 進來

TooPowerInbox 不附贈託管模型。面板預設跑本機啟發式。把 `agent.json` 指到你已經在付的那條路。

## 驅動

| `driver` | 它會呼叫什麼 |
|---|---|
| `local` | 內建分信。零網路。永遠當後備。 |
| `openai_compatible` | `POST {base_url}/chat/completions`（OpenAI、Ollama、vLLM、LiteLLM 等） |
| `cli` | 你自己的 argv。context pack 從 stdin 進去。 |
| `http` | 把 context pack `POST` 到你的 worker。回 `{ "answer": "…" }`。 |

把 `agent.example.json` 複製成 `agent.json`（安裝程式已經做了）。

### Ollama

```json
{
  "driver": "openai_compatible",
  "openai_compatible": {
    "base_url": "http://127.0.0.1:11434/v1",
    "model": "llama3.1",
    "api_key_env": "OPENAI_API_KEY"
  }
}
```

### Claude CLI／Codex／任何吃 stdin 的 Agent

```json
{
  "driver": "cli",
  "cli": { "command": ["claude", "-p"], "timeout_sec": 180 }
}
```

### 你自己的迴圈

1. `GET /api/v1/context?lang=zh-Hant` 拿人格、看板、近期信件。
2. 用 `POST /api/v1/tools/{name}` 叫工具。
3. 若還想用內建包一層，再 `POST /api/v1/agent/run`，body 加 `"lang": "zh-Hant"`。

工具：`list_inbox`、`brain_board`、`search_brain`、`persona`、`save_draft`。

不開放寄信。草稿只留在本機 SQLite。
