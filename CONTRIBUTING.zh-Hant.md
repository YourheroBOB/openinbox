# 怎麼一起改

[English](CONTRIBUTING.md) · 正體中文

TooPowerInbox 刻意保持小。

- `server/` 只用 Python 3.9 標準庫。除非是可選接線，不要加 pip。
- 不要加託管模型、遙測，也不要加會在沒有本機明示旗標時寄信的路徑。
- 示範信件必須是虛構的。倉庫裡不准出現真信箱。
- 新技能用雙語 markdown 放 `skills/`（正體中文在前，英文在後）。
- 新工具加在 `agent_bridge.TOOLS` 與 `invoke_tool`。
- 面板字串要同時寫進 `ui/index.html` 的 `zh-Hant` 與 `en`。禁止簡體。

```
./install.sh && OPENINBOX_NO_BROWSER=1 ./run.sh
curl -s http://127.0.0.1:8770/api/health
```
